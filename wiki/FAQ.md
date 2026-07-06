# FAQ

## My entities are unavailable. Why?

SEMS needs at least **6 hours** of price data to say anything meaningful.
If it finds fewer, it marks its entities unavailable instead of guessing,
and writes a warning to the Home Assistant log (search for "sems"). Usual
causes: the price entity is unavailable itself, or it isn't a supported
format — see [Configuration](Configuration.md).

## `sensor.sems_current_price` doesn't match what I pay

Almost always the **price type** setting:

- Your sensor provides all-in prices but SEMS is set to **Raw** → taxes get
  added twice → too high.
- Your sensor provides raw prices but SEMS is set to **All-in** → taxes
  missing → too low.

Fix it via **Settings → Devices & services → SEMS → Configure**. If the
price is only slightly off, adjust the supplier markup / energy tax / VAT
values to match your contract.

## Why do sunny hours score high even though my tariff is flat?

Because your own solar power is much cheaper than grid power — using it
only "costs" the missed export payment (a few cents) instead of the full
tariff. This is the core idea of SEMS: see
[How the score works](How-the-score-works.md).

## Why doesn't rank 24 exist this morning?

Tomorrow's prices are published around 13:00 CET. Before that, SEMS only
knows today's remaining hours — say 18 — and then ranks run from 1 to 18.
Check the `hours_available` attribute, or automate on
`sensor.sems_relative_score` (always 0–100%) instead.

## The score is above 100. Is that a bug?

No — that's **free power**. When the all-in price drops below the
free-power threshold (default €0.00), the score deliberately goes above 100
to signal "this beats every normal hour". The further below the threshold,
the higher the score. `binary_sensor.sems_free_power` is ON during these
hours.

## The market price is negative but free power is OFF. Why?

"Free" is judged on the price you actually pay, **taxes included**. A
market price of −€0.05 still becomes a *positive* all-in price after ~11
cents of taxes and VAT are added. You'll see the hour score very well
(the *effective* price is low), but it isn't free.

## I have no solar panels. Is SEMS useful?

Yes — leave the PV entity empty and SEMS becomes a pure price optimizer:
the score simply follows the (all-in) price, and rank/relative score work
the same way.

## Does SEMS send data anywhere or call the internet?

No. SEMS reads two sensors inside your Home Assistant and does math. No
external connections, no dependencies, no cloud.

## How often does SEMS update?

At the top of every hour, plus whenever one of your source sensors changes
(e.g. when tomorrow's prices arrive). Moving the balance slider also
recalculates immediately.

## Can SEMS control my devices directly?

No, by design. SEMS gives you honest numbers; your automations decide what
to do with them. See [Example automations](Example-automations.md) for
copy-paste starting points.

## Which solar forecast integrations are supported?

Any integration that can show a solar forecast on Home Assistant's Energy
dashboard — including core **Forecast.Solar** and **Solcast**. Pick any one
of its sensors as the PV forecast entity; SEMS finds the hourly data
itself. (Forecast.Solar's entities have no hourly attributes — that's
expected, SEMS fetches the forecast through the same official route the
Energy dashboard uses.) Integrations that expose hourly attributes on the
entity (`watts` dict or a Solcast-style `forecast` list) work too.

## Which price integrations are supported?

1. Any sensor with Nordpool-style `raw_today`/`raw_tomorrow` attributes
   (HACS Nord Pool, EnergyZero, and others).
2. Any sensor with a Frank Energie-style `prices` attribute (a list of
   `from`/`till`/`price` entries) — e.g. **Frank Energie**'s
   "Current electricity price (All-in)" sensor.
3. The core **Nord Pool** integration (SEMS uses its
   `get_prices_for_date` action behind the scenes).

Something else? Open an issue on GitHub — the parser was built to be easy
to extend.
