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

## Frank Energie has several price entities. Which one do I pick?

SEMS reads whatever entity you point it at — it cannot know which price
variant a sensor contains. So match the entity to the price type setting:

- Pick **"Current electricity price (All-in)"** and keep the price type
  on **All-in** (the default), or
- pick **"Current electricity market price"** and set the price type to
  **Raw**.

Two safety nets: `sensor.sems_current_price` should match what your
energy app says you pay right now, and the diagnostics sensor runs a
plausibility check — if the average price looks like a bare market price
while the price type says all-in (or the other way around), its state
changes to `CHECK SETTINGS - ...` with an explanation in the
`sanity_check` attribute.

## Frank Energie shows 15-minute prices, but SEMS shows one price per hour?

That's the hour-blocks resolution (the default): SEMS averages the four
quarters of each hour, so `sensor.sems_current_price` is the average of
the current hour. Prefer planning per quarter? Switch Configure →
Planning resolution to quarter-hour blocks.

## sensor.sems_rank says 6, but rank_today says this hour is 16. Which is right?

**Both.** They count on different scales:

- `sensor.sems_rank` ranks within a **rolling** window of the hours it
  currently knows. Check its `hours_available` attribute: at 10:00, before
  tomorrow's prices are published, that's only **14** hours (10:00–23:00).
  So "6" means *6th best of the 14 hours left today* — the scale is 1–14,
  not 1–24.
- `sensor.sems_rank_today` ranks within the **whole calendar day**, always
  24 blocks. So "16" means *16th best of all 24 hours of today* — it also
  counts this morning's hours, which `sems_rank` no longer includes.

Same maths, different reference set. If you want one stable number for
"how good is now", use the `current_rank` attribute of
`sensor.sems_rank_today` — that is always on a 1–24 scale.

## How do I report a problem with my numbers?

Go to **Settings → Devices & services → SEMS**, click the three dots and
choose **Download diagnostics**. The file contains your settings,
everything SEMS computed, and the raw attributes of your price and PV
entities — enough to replay your exact situation elsewhere. It contains no
passwords or tokens.

## My chart doesn't show all of tomorrow, even though the prices are known

The main sensor (`sensor.sems_relative_score` → `scores_24h`) uses a
**rolling 24-hour** window that always starts at the current hour, so in
the evening its tail reaches only into tomorrow morning — the rest of
tomorrow falls outside the window (it's not the PV forecast limiting it).

To see **all of today and tomorrow**, use the per-calendar-day sensors
`sensor.sems_rank_today` and `sensor.sems_rank_tomorrow` instead — each
holds a full day in its `scores` attribute, ranked 1–24 on its own. The
[Dashboard charts](Dashboard-charts.md) page has a ready-made
"rank per day" card built on them.

## My charts show a gap for tomorrow. Is that a bug?

No — those blocks have no published prices yet (they arrive around 13:00
CET). SEMS deliberately shows them as empty (`null`) instead of guessing.
Once the prices arrive, the gap fills in automatically.

## Hour blocks or quarter-hour blocks?

Hour blocks (the default) suit devices that shouldn't switch often, like
heat pumps. Quarter-hour blocks follow the 15-minute prices some
suppliers use — rank then runs 1–96 instead of 1–24. Change it any time
via Configure → Planning resolution.

## Why doesn't rank 24 exist this morning?

Tomorrow's prices are published around 13:00 CET. Before that, SEMS only
knows today's remaining hours — say 18 — and then ranks run from 1 to 18.
Check the `hours_available` attribute, or automate on
`sensor.sems_relative_score` (always 0–100%) instead.

## The relative score is 100. Is my power free now?

No! The relative score compares hours **within the coming day**: 100%
simply means "this is the best hour of the coming 24" — which happens
every day, also on expensive days. Free power is an absolute fact about
the price, with its own signals: `binary_sensor.sems_free_power` turns ON,
and the raw score (in the `scores_24h` attribute) goes above 100. See
[How the score works](How-the-score-works.md).

## A score in scores_24h is above 100. Is that a bug?

No — that's **free power**. When the all-in price drops below the
free-power threshold (default €0.00), the raw score deliberately goes
above 100 to signal "this beats every normal hour". The further below the
threshold, the higher the score. `binary_sensor.sems_free_power` is ON
during these hours.

## Where did sensor.sems_score go?

It still exists but is **disabled by default** since v0.1.7, because it
was easily confused with the relative score. Enable it via the SEMS device
page → the entity → settings (gear) → Enabled. The raw per-hour scores are
always available in the `scores_24h` attribute of
`sensor.sems_relative_score`.

## The market price is negative but free power is OFF. Why?

"Free" is judged on the price you actually pay, **taxes included**. A
market price of −€0.05 still becomes a *positive* all-in price after ~11
cents of taxes and VAT are added. You'll see the hour score very well
(the *effective* price is low), but it isn't free.

## I have no solar panels. Is SEMS useful?

Yes — leave the PV entity empty and SEMS becomes a pure price optimizer:
the score simply follows the (all-in) price, and rank/relative score work
the same way.

## The SEMS icon shows as a placeholder in Home Assistant

The SEMS logo ships inside the integration (`brand/` folder) and Home
Assistant picks it up automatically **from version 2026.3.0 onwards**. On
older versions custom integrations can't provide their own icon, so you'll
see the generic placeholder until you update Home Assistant. Nothing is
broken — it's purely cosmetic.

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
