"""Pure calculation functions for SEMS.

This module contains ONLY plain Python math — no Home Assistant imports at
all. That makes it possible to unit-test the entire scoring algorithm on any
machine with pytest, without installing Home Assistant.

The functions in this module:

* ``to_all_in_price``  — converts a raw market (spot) price into the all-in
  price a consumer actually pays, by adding supplier markup and energy tax
  and then applying VAT.
* ``to_raw_price``     — the exact inverse: estimates the raw market price
  hiding inside an all-in price. Needed to estimate what exporting earns
  when the user's price sensor already includes taxes.
* ``compute_scores``   — the heart of SEMS: given the hourly all-in prices,
  export prices, and PV forecast for the next ~24 hours, it computes a
  score per hour that says how attractive that hour is for using
  electricity.

The core idea of the scoring (the "effective price" model):

    What does one kWh REALLY cost you in a given hour?

    * In a dark hour you buy from the grid and pay the full all-in price
      (market price + supplier markup + energy tax + VAT).
    * In a sunny hour you consume your own solar power. That power is not
      free: you could have exported it. But exporting only earns the bare
      market price minus a feed-in fee — no taxes come back. So consuming
      your own solar power only "costs" you that small missed payment.
    * Partly sunny hours sit proportionally in between.

    Example (typical Dutch dynamic contract): all-in price 0.28 €/kWh, of
    which only 0.08 is market price. Exporting earns 0.08 - 0.02 fee =
    0.06 €/kWh. So a fully sunny hour effectively costs 0.06 while a dark
    hour costs 0.28 — running the dishwasher in the sun is by far the
    cheapest, even on a flat tariff.
"""

from __future__ import annotations


def to_all_in_price(
    raw_price: float,
    supplier_markup: float,
    energy_tax: float,
    vat_percent: float,
) -> float:
    """Convert a raw market price (€/kWh) into an all-in consumer price (€/kWh).

    The all-in price is what a consumer actually pays per kWh:

        all_in = (raw_price + supplier_markup + energy_tax) * (1 + vat_percent / 100)

    Note that supplier markup and energy tax are added even when the raw
    price is negative. That is intentional and matches reality: with a spot
    price of -0.05 €/kWh, Dutch consumers still pay markup + energy tax + VAT,
    so the all-in price can easily be positive while the market price is
    negative.
    """
    return (raw_price + supplier_markup + energy_tax) * (1 + vat_percent / 100)


def to_raw_price(
    all_in_price: float,
    supplier_markup: float,
    energy_tax: float,
    vat_percent: float,
) -> float:
    """Estimate the raw market price (€/kWh) inside an all-in price (€/kWh).

    This is the exact mathematical inverse of ``to_all_in_price``:

        raw = all_in / (1 + vat_percent / 100) - supplier_markup - energy_tax

    SEMS needs this when the user's price sensor already provides all-in
    prices: to know what EXPORTING a kWh earns, we have to strip the taxes
    back off, because exported power only pays out the bare market price.
    """
    return all_in_price / (1 + vat_percent / 100) - supplier_markup - energy_tax


def find_best_block(scores: list[float], length: int) -> int | None:
    """Find the best consecutive run of ``length`` blocks.

    Given the per-block scores of the window, return the START INDEX of the
    consecutive run of ``length`` blocks with the highest AVERAGE score —
    the best moment to start an appliance that needs that long to finish
    (e.g. a dishwasher needing 2 hours).

    Ties are broken in favour of the earliest start. Returns ``None`` when
    there are fewer than ``length`` blocks available (the appliance would
    not fit inside the known data) or when ``length`` is not positive.
    """
    n = len(scores)
    if length <= 0 or length > n:
        return None

    # Rolling sum over the window: highest sum == highest average.
    best_start = 0
    best_sum = current = sum(scores[:length])
    for start in range(1, n - length + 1):
        # Slide the window one block: drop the left value, add the right.
        current += scores[start + length - 1] - scores[start - 1]
        if current > best_sum:
            best_sum = current
            best_start = start
    return best_start


def compute_scores(
    prices: list[float],
    export_prices: list[float],
    pv: list[float],
    balance: int,
    price_free_threshold: float,
    pv_capacity: float = 0.0,
) -> list[dict]:
    """Compute an attractiveness score for every hour in the window.

    Arguments:
        prices:  all-in electricity prices in €/kWh (what buying from the
                 grid costs), one per hour, starting at the current hour.
                 Usually 24 values, but fewer is fine (e.g. before ~13:00
                 CET tomorrow's prices are not known yet).
        export_prices: what exporting one kWh earns in that hour (€/kWh),
                 normally the raw market price minus the feed-in fee. Can be
                 negative (during negative market prices you PAY to export).
                 Aligned with ``prices``; missing hours fall back to the
                 all-in price of that hour.
        pv:      forecast PV production in Watts, one per hour, aligned with
                 ``prices``. If shorter than ``prices`` the missing hours are
                 treated as 0 W; extra hours are ignored.
        balance: the 0–100 slider. 100 = only the (effective) price matters,
                 0 = only PV self-consumption matters, 50 = both equally.
        price_free_threshold: below this ALL-IN price, power counts as
                 "free" and the hour gets a bonus score above 100.
        pv_capacity: total installed PV capacity in Watt-peak (e.g. 5000
                 for a 5 kWp system). Used to estimate how much of the
                 consumption is covered by own solar power in each hour.
                 0 (the default) means unknown: SEMS then assumes the
                 sunniest forecast hour of the window covers consumption
                 fully — fine on sunny days, too optimistic on gloomy
                 ones. Setting the real capacity fixes that.

    Returns:
        One dict per hour with keys:
            price           — the all-in price for this hour (€/kWh)
            export_price    — what exporting earns this hour (€/kWh)
            effective_price — what consuming a kWh really costs this hour
                              (€/kWh), see the module docstring
            pv              — the PV forecast used for this hour (W)
            score           — final absolute score (0–100, or >100 for
                              "free power" hours)
            relative_score  — 0–100 (%), this hour relative to the best and
                              worst hour in the window
            rank            — unique integer 1..N (1 = worst hour, N = best)

    The list is empty when ``prices`` is empty. This function never raises
    on odd-but-valid input (flat prices, all-zero PV, negative prices).
    """
    n = len(prices)
    if n == 0:
        return []

    # Align the helper lists with the price list:
    # * missing PV hours count as 0 W (no sun),
    # * missing export prices fall back to the all-in price of that hour
    #   (which makes the effective price equal the all-in price — neutral),
    # * extra hours beyond the price window are ignored.
    pv = (list(pv) + [0.0] * n)[:n]
    export_prices = (list(export_prices) + list(prices))[:n]

    # pv_max is computed over the SAME rolling window as the scores
    # (current hour + following hours), never over "today".
    pv_max = max(pv)

    # -----------------------------------------------------------------
    # Effective price per hour: what does one kWh really cost you?
    #
    # coverage (0..1) estimates how much of your consumption is covered by
    # your own solar power in this hour:
    #
    #   * With a known pv_capacity: forecast / capacity, capped at 1. A
    #     600 W forecast hour on a 5000 Wp system then correctly counts as
    #     barely covering anything, even if it is the best hour of a
    #     gloomy day.
    #   * Without (pv_capacity == 0): forecast / sunniest hour of the
    #     window — i.e. assume the best hour of the day covers consumption.
    #
    #   effective = (1 - coverage) * all_in_price  (the part you buy)
    #             +      coverage  * export_price  (the part that is your
    #                                               own power; it only costs
    #                                               the missed export payment)
    #
    # A dark hour costs the full all-in price. A fully covered hour only
    # costs the small missed export payment. This also handles extreme
    # price spikes correctly: when the market price is very high, exporting
    # earns a lot, so the effective price of a sunny hour rises and it can
    # become smarter to export then and consume in a cheaper hour instead.
    #
    # Note that base_pv (the sun-points component of the score) stays
    # normalised on the sunniest hour of the WINDOW, deliberately: with the
    # balance slider towards PV the user asks "follow the sun", and the
    # sunniest hour of a gloomy day is still the sunniest hour.
    # -----------------------------------------------------------------
    base_pvs: list[float] = []
    effective: list[float] = []
    for h in range(n):
        base_pv = 0.0 if pv_max <= 0 else pv[h] / pv_max
        base_pvs.append(base_pv)
        if pv_capacity > 0:
            coverage = min(1.0, pv[h] / pv_capacity)
        else:
            coverage = base_pv
        effective.append((1 - coverage) * prices[h] + coverage * export_prices[h])

    # Window aggregates of the effective price, for normalisation below.
    eff_max = max(effective)
    eff_min = min(effective)

    # The slider is split into two weights that always add up to 100.
    weight_price = balance
    weight_pv = 100 - balance

    results: list[dict] = []
    for h in range(n):
        # base_price: 1 for the (effectively) cheapest hour in the window,
        # 0 for the most expensive one. With a completely flat effective
        # price every hour is equally good, so fall back to a neutral 0.5.
        if eff_max == eff_min:
            base_price = 0.5
        else:
            base_price = (eff_max - effective[h]) / (eff_max - eff_min)

        # Weighted sum: each component contributes 0..weight points, so the
        # total is always 0..100.
        intermediate = base_price * weight_price + base_pvs[h] * weight_pv

        # "Free power" hours (ALL-IN price below the free threshold — this
        # deliberately uses the real all-in price, not the effective price)
        # get a bonus score above 100: the further below the threshold, the
        # higher the score. All other hours are clamped to 0..100.
        if prices[h] < price_free_threshold:
            score = 100 + (price_free_threshold - prices[h]) * 100
        else:
            score = min(100.0, max(0.0, intermediate))

        results.append(
            {
                "price": prices[h],
                "export_price": export_prices[h],
                "effective_price": effective[h],
                "pv": pv[h],
                "score": score,
            }
        )

    # -----------------------------------------------------------------
    # Ranking: unique ranks 1..N, 1 = lowest (worst) score.
    # Python's sort is stable, so hours with an identical score keep their
    # chronological order — the earlier hour gets the lower rank.
    # -----------------------------------------------------------------
    order = sorted(range(n), key=lambda i: results[i]["score"])
    for rank, index in enumerate(order, start=1):
        results[index]["rank"] = rank

    # -----------------------------------------------------------------
    # Relative score: where does each hour sit between the worst (0) and
    # best (100) hour of the window? With identical scores everywhere
    # there is no "better" or "worse", so use a neutral 50.
    # -----------------------------------------------------------------
    score_max = max(r["score"] for r in results)
    score_min = min(r["score"] for r in results)
    for r in results:
        if score_max == score_min:
            r["relative_score"] = 50.0
        else:
            r["relative_score"] = (r["score"] - score_min) / (score_max - score_min) * 100

    return results
