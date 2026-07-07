"""Unit tests for the pure SEMS calculation functions.

These tests run on plain Python + pytest — no Home Assistant required.
They load calculator.py directly from its file path instead of importing
the ``custom_components.simple_ems`` package, because the package __init__.py
will later import Home Assistant (which is not installed on a normal
development machine).
"""

import importlib.util
from pathlib import Path

import pytest

# Load calculator.py straight from disk (see module docstring for why).
_CALC_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "simple_ems"
    / "calculator.py"
)
_spec = importlib.util.spec_from_file_location("sems_calculator", _CALC_PATH)
calculator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(calculator)

compute_scores = calculator.compute_scores
to_all_in_price = calculator.to_all_in_price
to_raw_price = calculator.to_raw_price


# ---------------------------------------------------------------------------
# to_all_in_price / to_raw_price
# ---------------------------------------------------------------------------


def test_to_all_in_price_dutch_2026_defaults():
    """A typical positive spot price with the Dutch 2026 default taxes."""
    # (0.10 + 0.020 + 0.0916) * 1.21 = 0.256036
    assert to_all_in_price(0.10, 0.020, 0.0916, 21) == pytest.approx(0.256036)


def test_to_all_in_price_negative_raw_price_can_be_positive():
    """Taxes and VAT still apply to negative spot prices.

    With a spot price of -0.05 €/kWh the consumer still pays markup and
    energy tax, so the all-in price ends up positive.
    """
    # (-0.05 + 0.020 + 0.0916) * 1.21 = 0.074536
    result = to_all_in_price(-0.05, 0.020, 0.0916, 21)
    assert result == pytest.approx(0.074536)
    assert result > 0


def test_to_all_in_price_deeply_negative_stays_negative():
    """A very negative spot price stays negative even after taxes."""
    result = to_all_in_price(-0.50, 0.020, 0.0916, 21)
    assert result == pytest.approx((-0.50 + 0.020 + 0.0916) * 1.21)
    assert result < 0


def test_to_all_in_price_no_taxes_is_identity():
    """With zero markup, zero tax and zero VAT nothing changes."""
    assert to_all_in_price(0.25, 0.0, 0.0, 0) == pytest.approx(0.25)


def test_to_raw_price_is_exact_inverse():
    """Converting raw -> all-in -> raw must return the original price."""
    for raw in (-0.10, 0.0, 0.08, 0.35):
        all_in = to_all_in_price(raw, 0.020, 0.0916, 21)
        assert to_raw_price(all_in, 0.020, 0.0916, 21) == pytest.approx(raw)


def test_to_raw_price_typical_dutch_example():
    """An all-in price of ~0.28 hides a market price of ~0.12."""
    raw = to_raw_price(0.28, 0.020, 0.0916, 21)
    assert raw == pytest.approx(0.28 / 1.21 - 0.020 - 0.0916)


# ---------------------------------------------------------------------------
# compute_scores — basic structure
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty_list():
    assert compute_scores([], [], [], 50, 0.0) == []


def test_returns_one_dict_per_hour_with_all_keys():
    prices = [0.10, 0.20, 0.30, 0.15]
    exports = [0.02, 0.10, 0.18, 0.06]
    pv = [0, 500, 1000, 200]
    result = compute_scores(prices, exports, pv, 50, 0.0)
    assert len(result) == 4
    for entry in result:
        assert set(entry) == {
            "price",
            "export_price",
            "effective_price",
            "pv",
            "score",
            "relative_score",
            "rank",
        }


def test_pv_list_shorter_than_prices_is_padded_with_zeros():
    """Missing PV hours count as 0 W instead of crashing."""
    result = compute_scores([0.10, 0.20, 0.30], [0.0] * 3, [800.0], 50, 0.0)
    assert result[0]["pv"] == 800.0
    assert result[1]["pv"] == 0.0
    assert result[2]["pv"] == 0.0


def test_missing_export_prices_fall_back_to_all_in_price():
    """Without export prices the effective price equals the all-in price."""
    result = compute_scores([0.10, 0.30], [], [1000.0, 1000.0], 100, 0.0)
    assert result[0]["effective_price"] == pytest.approx(0.10)
    assert result[1]["effective_price"] == pytest.approx(0.30)


def test_pv_list_longer_than_prices_is_truncated():
    result = compute_scores([0.10, 0.20], [0.0, 0.0], [100.0, 200.0, 300.0], 50, 0.0)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# compute_scores — effective price model
# ---------------------------------------------------------------------------


def test_effective_price_blends_grid_and_export_price():
    """A fully sunny hour costs the export price, a dark hour the all-in
    price, and a half-sunny hour sits exactly in between."""
    prices = [0.28, 0.28, 0.28]
    exports = [0.06, 0.06, 0.06]
    pv = [0.0, 2000.0, 1000.0]  # dark, sunniest, half as sunny
    result = compute_scores(prices, exports, pv, 50, 0.0)
    assert result[0]["effective_price"] == pytest.approx(0.28)
    assert result[1]["effective_price"] == pytest.approx(0.06)
    assert result[2]["effective_price"] == pytest.approx(0.17)


def test_flat_tariff_still_prefers_sunny_hours_at_balance_100():
    """The user's core scenario: a flat 0.28 tariff all day.

    Even a purely price-driven user (balance=100) should prefer the sunny
    hours, because self-consumed solar power only costs the missed export
    payment (~0.06) instead of the full 0.28 grid price.
    """
    prices = [0.28, 0.28, 0.28, 0.28]
    exports = [0.06, 0.06, 0.06, 0.06]
    pv = [0.0, 0.0, 2000.0, 1000.0]
    result = compute_scores(prices, exports, pv, 100, 0.0)
    # Sunniest hour: effective 0.06 -> best score.
    assert result[2]["score"] == pytest.approx(100.0)
    # Half sunny: effective 0.17 -> exactly halfway.
    assert result[3]["score"] == pytest.approx(50.0)
    # Dark hours: effective 0.28 -> worst.
    assert result[0]["score"] == pytest.approx(0.0)
    assert result[1]["score"] == pytest.approx(0.0)
    assert result[2]["rank"] == 4


def test_extreme_price_spike_makes_exporting_win():
    """During an extreme price spike, exporting earns so much that it is
    smarter to consume in a cheap dark hour and sell the solar power."""
    # Hour 0: cheap dark night (all-in 0.20). Hour 1: spike, sunny, exporting
    # earns 0.58 — more than the night price.
    prices = [0.20, 0.86]
    exports = [0.03, 0.58]
    pv = [0.0, 2000.0]
    result = compute_scores(prices, exports, pv, 100, 0.0)
    # Effective prices: night 0.20 vs sunny spike hour 0.58.
    assert result[0]["effective_price"] == pytest.approx(0.20)
    assert result[1]["effective_price"] == pytest.approx(0.58)
    # At balance 100 the cheap night wins.
    assert result[0]["score"] > result[1]["score"]
    # At balance 0 (pure self-consumption) the sunny hour still wins.
    result_pv = compute_scores(prices, exports, pv, 0, 0.0)
    assert result_pv[1]["score"] > result_pv[0]["score"]


def test_negative_export_price_makes_sunny_hour_extra_attractive():
    """With a negative market price you PAY to export, so consuming your
    own solar power is extra attractive: the effective price goes negative."""
    prices = [0.05, 0.20]  # all-in prices still positive
    exports = [-0.07, 0.06]
    pv = [3000.0, 0.0]
    result = compute_scores(prices, exports, pv, 100, 0.0)
    assert result[0]["effective_price"] == pytest.approx(-0.07)
    assert result[0]["score"] == pytest.approx(100.0)
    # But it is NOT "free power": the all-in price is still positive.
    assert result[0]["score"] <= 100.0


# ---------------------------------------------------------------------------
# compute_scores — installed PV capacity (pv_capacity)
# ---------------------------------------------------------------------------


def test_pv_capacity_makes_gloomy_day_realistic():
    """A gloomy winter day: the 'best' hour only produces 600 W on a
    5000 Wp system. That barely covers any consumption, so the effective
    price must stay close to the grid price — not drop to the export price.
    """
    prices = [0.28, 0.28, 0.28]
    exports = [0.06, 0.06, 0.06]
    pv = [0.0, 600.0, 300.0]
    result = compute_scores(prices, exports, pv, 100, 0.0, pv_capacity=5000)
    # coverage = 600/5000 = 0.12 -> effective = 0.88*0.28 + 0.12*0.06
    assert result[1]["effective_price"] == pytest.approx(0.88 * 0.28 + 0.12 * 0.06)
    assert result[1]["effective_price"] > 0.25  # close to grid price
    # Without capacity the same hour would (wrongly) get the full export price.
    without = compute_scores(prices, exports, pv, 100, 0.0)
    assert without[1]["effective_price"] == pytest.approx(0.06)


def test_pv_capacity_zero_keeps_window_max_behaviour():
    """pv_capacity=0 (the default) means: assume the sunniest hour of the
    window covers consumption — the original behaviour."""
    prices = [0.28, 0.28]
    exports = [0.06, 0.06]
    pv = [0.0, 4000.0]
    result = compute_scores(prices, exports, pv, 100, 0.0, pv_capacity=0)
    assert result[1]["effective_price"] == pytest.approx(0.06)


def test_pv_forecast_above_capacity_is_capped():
    """Coverage can never exceed 100%, even if the forecast exceeds the
    configured capacity (e.g. slightly optimistic forecasts)."""
    result = compute_scores([0.28], [0.06], [6000.0], 100, 0.0, pv_capacity=5000)
    assert result[0]["effective_price"] == pytest.approx(0.06)


def test_pv_capacity_does_not_change_sun_points():
    """The balance-0 'follow the sun' component stays normalised on the
    sunniest hour of the window: even on a gloomy day, the best sun hour
    scores 100 when only PV matters."""
    prices = [0.28, 0.28, 0.28]
    exports = [0.06, 0.06, 0.06]
    pv = [0.0, 600.0, 300.0]
    result = compute_scores(prices, exports, pv, 0, 0.0, pv_capacity=5000)
    assert result[1]["score"] == pytest.approx(100.0)
    assert result[2]["score"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# compute_scores — flat window
# ---------------------------------------------------------------------------


def test_flat_prices_no_pv_neutral_scores():
    """A flat tariff without any sun: every hour is equally good.

    base_price falls back to 0.5, so with balance=50 every hour scores
    0.5 * 50 = 25. All scores are equal, so relative_score is 50.
    """
    prices = [0.25] * 24
    result = compute_scores(prices, [0.10] * 24, [0.0] * 24, 50, 0.0)
    for entry in result:
        assert entry["score"] == pytest.approx(25.0)
        assert entry["relative_score"] == pytest.approx(50.0)


def test_flat_prices_ranks_are_unique_and_chronological():
    """Ties are broken by hour order: earlier hour gets the lower rank."""
    result = compute_scores([0.25] * 24, [0.10] * 24, [0.0] * 24, 50, 0.0)
    assert [entry["rank"] for entry in result] == list(range(1, 25))


# ---------------------------------------------------------------------------
# compute_scores — no PV
# ---------------------------------------------------------------------------


def test_pv_max_zero_means_no_pv_points():
    """With no sun (or no PV entity), only the price component scores.

    With balance=50 the maximum reachable score is weight_price=50 for the
    cheapest hour, and the effective price equals the all-in price.
    """
    prices = [0.10, 0.30, 0.20]
    result = compute_scores(prices, [0.0, 0.2, 0.1], [0.0, 0.0, 0.0], 50, 0.0)
    assert result[0]["score"] == pytest.approx(50.0)  # cheapest: base_price 1.0
    assert result[1]["score"] == pytest.approx(0.0)  # most expensive
    assert result[2]["score"] == pytest.approx(25.0)  # halfway
    assert [e["rank"] for e in result] == [3, 1, 2]
    # No sun -> effective price is simply the all-in price.
    assert [e["effective_price"] for e in result] == pytest.approx(prices)


# ---------------------------------------------------------------------------
# compute_scores — negative prices and free power
# ---------------------------------------------------------------------------


def test_negative_prices_without_free_bonus_score_normally():
    """Negative all-in prices work fine in the normal formula.

    The free threshold is set below every price so the bonus path never
    triggers; the cheapest (most negative) hour is simply the best hour.
    """
    prices = [-0.10, 0.00, 0.10]
    result = compute_scores(prices, list(prices), [0.0] * 3, 100, -1.0)
    assert result[0]["score"] == pytest.approx(100.0)
    assert result[1]["score"] == pytest.approx(50.0)
    assert result[2]["score"] == pytest.approx(0.0)


def test_free_power_hours_score_above_100():
    """Hours with an all-in price below the free threshold get a bonus
    score above 100 — the further below, the higher."""
    prices = [-0.10, -0.02, 0.20]
    result = compute_scores(prices, list(prices), [0.0] * 3, 50, 0.0)
    # score = 100 + (threshold - price) * 100
    assert result[0]["score"] == pytest.approx(110.0)
    assert result[1]["score"] == pytest.approx(102.0)
    assert result[2]["score"] <= 100.0
    # The further below the threshold, the higher the score (and rank).
    assert result[0]["rank"] == 3
    assert result[1]["rank"] == 2
    assert result[2]["rank"] == 1


def test_price_exactly_at_free_threshold_is_not_free():
    """The comparison is strictly 'below': exactly 0.00 is not free."""
    result = compute_scores([0.00, 0.10], [0.0, 0.1], [0.0, 0.0], 50, 0.0)
    assert result[0]["score"] <= 100.0


# ---------------------------------------------------------------------------
# compute_scores — balance slider
# ---------------------------------------------------------------------------

# One shared scenario: hour 0 is cheap without sun, hour 1 is expensive and
# sunny, hour 2 is mid-priced with some sun. Export prices roughly follow
# the market part of the all-in price minus a 0.02 fee.
SCENARIO_PRICES = [0.05, 0.35, 0.20]
SCENARIO_EXPORTS = [-0.07, 0.16, 0.03]
SCENARIO_PV = [0.0, 2000.0, 1000.0]


def test_balance_100_only_effective_price_matters():
    """balance=100: scores follow the effective price exactly."""
    result = compute_scores(SCENARIO_PRICES, SCENARIO_EXPORTS, SCENARIO_PV, 100, 0.0)
    # Effective prices: h0 = 0.05 (dark), h1 = 0.16 (fully sunny -> export
    # price), h2 = 0.5*0.20 + 0.5*0.03 = 0.115.
    assert result[0]["effective_price"] == pytest.approx(0.05)
    assert result[1]["effective_price"] == pytest.approx(0.16)
    assert result[2]["effective_price"] == pytest.approx(0.115)
    # Cheapest effective hour wins, most expensive loses.
    assert result[0]["score"] == pytest.approx(100.0)
    assert result[1]["score"] == pytest.approx(0.0)
    expected_mid = (0.16 - 0.115) / (0.16 - 0.05) * 100
    assert result[2]["score"] == pytest.approx(expected_mid)
    assert result[0]["rank"] == 3


def test_balance_0_only_pv_matters():
    """balance=0: only self-consumption counts — the sunniest hour wins."""
    result = compute_scores(SCENARIO_PRICES, SCENARIO_EXPORTS, SCENARIO_PV, 0, 0.0)
    assert result[1]["score"] == pytest.approx(100.0)  # base_pv = 1
    assert result[2]["score"] == pytest.approx(50.0)  # base_pv = 0.5
    assert result[0]["score"] == pytest.approx(0.0)  # no sun
    assert result[1]["rank"] == 3


def test_balance_50_blends_both_components():
    """balance=50: score = base_price * 50 + base_pv * 50."""
    result = compute_scores(SCENARIO_PRICES, SCENARIO_EXPORTS, SCENARIO_PV, 50, 0.0)
    effective = [0.05, 0.16, 0.115]
    eff_max, eff_min = max(effective), min(effective)
    pv_max = max(SCENARIO_PV)
    for h in range(3):
        base_price = (eff_max - effective[h]) / (eff_max - eff_min)
        base_pv = SCENARIO_PV[h] / pv_max
        expected = base_price * 50 + base_pv * 50
        assert result[h]["score"] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# compute_scores — fewer than 24 hours
# ---------------------------------------------------------------------------


def test_short_window_still_produces_full_output():
    """Before tomorrow's prices are published the window is shorter than 24h.

    The function simply scores the hours that ARE available.
    """
    prices = [0.10, 0.20, 0.30, 0.05, 0.15, 0.25]  # only 6 hours known
    result = compute_scores(prices, list(prices), [0.0] * 6, 50, 0.0)
    assert len(result) == 6
    assert sorted(e["rank"] for e in result) == [1, 2, 3, 4, 5, 6]
    # The cheapest of the 6 hours is the best hour of this short window.
    assert result[3]["rank"] == 6
    assert result[3]["relative_score"] == pytest.approx(100.0)


def test_single_hour_window():
    """Even a single known hour must not crash (flat-window fallbacks)."""
    result = compute_scores([0.20], [0.05], [500.0], 50, 0.0)
    assert len(result) == 1
    assert result[0]["rank"] == 1
    assert result[0]["relative_score"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# find_best_block
# ---------------------------------------------------------------------------

find_best_block = calculator.find_best_block


def test_find_best_block_picks_highest_average_run():
    """The 2-block run 80+90 beats every other consecutive pair."""
    scores = [10.0, 40.0, 80.0, 90.0, 30.0, 20.0]
    assert find_best_block(scores, 2) == 2


def test_find_best_block_single_block_is_maximum():
    scores = [10.0, 40.0, 80.0, 90.0, 30.0]
    assert find_best_block(scores, 1) == 3


def test_find_best_block_whole_window():
    """A run as long as the window can only start at 0."""
    assert find_best_block([1.0, 2.0, 3.0], 3) == 0


def test_find_best_block_tie_prefers_earliest_start():
    scores = [50.0, 50.0, 50.0, 50.0]
    assert find_best_block(scores, 2) == 0


def test_find_best_block_too_long_returns_none():
    """An appliance that does not fit in the known data gets no block."""
    assert find_best_block([10.0, 20.0], 3) is None
    assert find_best_block([], 1) is None
    assert find_best_block([10.0], 0) is None
