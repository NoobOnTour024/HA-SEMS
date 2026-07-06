# Entities

After setup you'll find one **SEMS device** (Settings → Devices & services →
SEMS) with these entities. Everything updates at the top of every hour and
whenever a source sensor changes.

## `sensor.sems_score`

The absolute score of the **current hour**: 0 (worst) to 100 (best), and
above 100 during free-power hours.

Attributes:

- **`scores_24h`** — the full window as a list, one entry per hour:

  ```yaml
  - start: "2026-07-06T13:00:00+02:00"
    price: 0.07        # all-in price, €/kWh
    pv: 4600           # forecast solar production, W
    score: 98.9
    relative_score: 96.7
    rank: 24
  ```

  This is the attribute to build charts and smarter automations on (see
  [Example automations](Example-automations.md)).
- **`hours_available`** — how many hours of price data the window currently
  holds (24 after tomorrow's prices are published, fewer before that).

## `sensor.sems_relative_score`

The current hour as a percentage between the worst (0%) and best (100%)
hour of the window. Handy for "only run when we're in the top half of the
day" conditions (`above: 50`).

## `sensor.sems_rank`

The current hour's rank within the window: **1 = worst, 24 = best**. Ranks
are unique — no two hours share a rank. Great for automations: "rank above
19" always means "one of the 5 best hours of the coming day".

Attribute `hours_available`: with fewer than 24 known hours, the best
possible rank is lower too (e.g. 18 when 18 hours are known).

## `sensor.sems_current_price`

The **all-in** price of the current hour in €/kWh — the exact number all
thresholds and scores are based on. Use it to verify SEMS' tax conversion
against your supplier's app.

Attributes: `price_type` (all_in/raw as configured), `export_price` (what
exporting earns this hour), `effective_price` (what a kWh really costs you
this hour — see [How the score works](How-the-score-works.md)).

## `binary_sensor.sems_free_power`

**ON** when the current all-in price is below the free-power threshold
(default €0.00) — in other words, when you get paid (or pay nothing) to
consume. Derived directly from the price, never from the score.

Attributes: `current_price`, `threshold`.

## `number.sems_balance`

The 0–100 slider that defines what a "good hour" means:

| Value | Meaning |
|---|---|
| 100 | Only the (effective) price matters — cheapest hours win. |
| 50 | Price and solar self-consumption matter equally (default). |
| 0 | Only solar production matters — sunniest hours win. |

Changes take effect immediately and survive restarts.

## `sensor.sems_diagnostics` (debug mode only)

A **temporary verification aid**, created only while debug mode is enabled
in the options. The state is a plain-language health message, e.g.:

> `OK - 24h of prices, PV forecast found (peak 4600 W)`

The attributes show where the data came from (`price_source`, `pv_source`)
and an `hourly_overview`: one row per hour with the PV forecast, the raw
market price, the all-in price, the export price, the effective price, the
score and the rank. If a number ever looks off, this is where you check
what SEMS is actually working with — see
[Check that it works](Check-that-it-works.md).

Turn debug mode off via **Configure** once you trust the numbers — the
sensor disappears.
