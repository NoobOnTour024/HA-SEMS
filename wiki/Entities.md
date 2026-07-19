# Entities

After setup you'll find one **SEMS device** (Settings → Devices & services →
SEMS) with these entities. Everything updates at the top of every hour and
whenever a source sensor changes.

## `sensor.sems_relative_score`

**The main SEMS sensor.** The current hour as a percentage between the
worst (0%) and best (100%) hour of the coming 24 hours. Handy for "only
run when we're in the top half of the day" conditions (`above: 50`).

> ⚠️ **100% does not mean free power.** Every day has exactly one
> best hour, so the relative score reaches 100 every single day — also on
> an expensive day. It only says: *of the coming 24 hours, this one is the
> best.* Free power has its own signal: `binary_sensor.sems_free_power`.

Attributes:

- **`scores_24h`** — the full window as a list, one entry per hour:

  ```yaml
  - start: "2026-07-06T13:00:00+02:00"
    price: 0.07             # all-in price, €/kWh
    effective_price: -0.03  # what a kWh really costs you, €/kWh
    pv: 4600                # forecast solar production, W
    score: 98.9             # raw score (above 100 = free power)
    relative_score: 96.7
    rank: 24
  ```

  This is the attribute to build charts and smarter automations on (see
  [Dashboard charts](Dashboard-charts.md) and
  [Example automations](Example-automations.md)).

  The list always spans the full 24-hour window. Blocks whose prices are
  **not published yet** (typically tomorrow, before ~13:00 CET) appear
  with `null` values — charts show a gap there, nothing is guessed.
- **`best_blocks`** — the best consecutive 2/3/4-hour runs, with their
  planned start/end and average score (see the block sensors below).
- **`hours_available`** — how many hours of price data the window currently
  holds (24 after tomorrow's prices are published, fewer before that).
- **`block_minutes`** — 60 (hour blocks, default) or 15 (quarter-hour
  blocks), following the resolution setting.

## `sensor.sems_rank`

The current block's rank **within today**: **1 = worst, 24 = best** (or
**1–96** with quarter-hour resolution). Ranks are unique — no two blocks
share a rank. It's ranked against the whole calendar day, so the scale is
a stable 1–24 from midnight to midnight: "rank above 19" means "one of
the 5 best hours of today" at any time of day, morning included.

Attributes:

- **`scores`** — the big one: **today and tomorrow back to back** (up to
  48 hours), one entry per block with `start`, `price`, `effective_price`,
  `pv`, `score`, `relative_score` and `rank` (each day ranked 1–24 on its
  own). This is what charts and per-day automations read; because the
  timestamps carry the day, the rank resets to 1 at midnight. Today
  includes the hours that already passed; tomorrow's entries appear once
  its prices are published (~13:00 CET). *(Not stored in the recorder
  database — it's a forecast; the live value is always available.)*
- **`current_rank`** — the same value as the state (the current block's
  rank within today), handy in templates.
- **`best_hour_today`** / **`best_hour_tomorrow`** — the ISO start of each
  day's single best (rank-highest) block. `best_hour_tomorrow` is `null`
  until tomorrow's prices publish.
- `hours_available` — how many blocks of today are ranked (normally 24;
  the highest reachable rank). `ranked_within` — `today` normally; only
  `rolling window (fallback)` in the rare case a price source doesn't
  publish the current hour as part of today. `block_minutes` — 60 or 15.

Example: start the boiler in tomorrow's single best hour, straight from
`best_hour_tomorrow`:

```yaml
automation:
  - alias: "Boiler in tomorrow's best hour"
    trigger:
      - platform: time_pattern
        minutes: 0
    condition:
      - condition: template
        value_template: >
          {% set best = state_attr('sensor.sems_rank', 'best_hour_tomorrow') %}
          {{ best is not none
             and as_datetime(best) == now().replace(minute=0, second=0, microsecond=0) }}
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.boiler
```

> **Changed over time.** Until v0.4.0 this ranked within the *rolling*
> window, whose scale shrank in the morning (only 14 at 10:00), so "rank
> above 19" could never fire before noon. v0.5.0 merged the separate
> `sensor.sems_rank_today` / `sensor.sems_rank_tomorrow` sensors into the
> `scores` attribute here — if you had those on a dashboard, point the
> cards at `sensor.sems_rank` instead. The rolling per-block ranks are
> still in the `scores_24h` attribute of `sensor.sems_relative_score`.

## `binary_sensor.sems_best_2h_block` (and 3h, 4h)

For appliances that need **more than one block** to finish — a dishwasher
that runs 2 hours, a washing machine cycle of 3. Each sensor finds the
best *consecutive* run of that length in the coming window and turns
**ON** when that run starts now: the moment to switch the appliance on.

Attributes: `planned_start`, `planned_end` and `average_score` of the
best run — always visible, so you can also automate on the start time or
show the plan on a dashboard. Because SEMS re-plans every block, the
planned start can shift when new prices arrive.

```yaml
automation:
  - alias: "Dishwasher in the best 2-hour window"
    trigger:
      - platform: state
        entity_id: binary_sensor.sems_best_2h_block
        to: "on"
    condition:
      - condition: state
        entity_id: input_boolean.dishwasher_ready
        state: "on"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.dishwasher
```

## `sensor.sems_score` (advanced — disabled by default)

The raw internal score of the current hour: 0–100, and **above 100 during
free-power hours** (105 = 5 cents below the free threshold, and so on).

This sensor is disabled by default because it is easily confused with the
relative score. The honest truth: the raw score is *also* relative to the
coming 24 hours (the cheapest effective hour of the window defines the
top). The relative score is simply the raw score stretched so the worst
hour is exactly 0 and the best exactly 100. The only extra information in
the raw score: on a day where all hours are nearly equal, raw scores
cluster together (say, all between 24 and 30) while the relative score
still spans 0–100 — the raw score then tells you "today it hardly
matters", where the relative score exaggerates tiny differences.

Need it anyway? Enable it: the SEMS device page → this entity → settings
(gear) → *Enabled*. The per-hour raw scores are always available in
`scores_24h` on the relative score sensor, whether this entity is enabled
or not.

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

## `binary_sensor.sems_pause_now`

The mirror image of the best-block sensors: those say "start now", this one
says **"switch off now"**. For devices where the win is skipping the
expensive hours rather than catching the cheap ones — a freezer, a boiler,
a circulation pump.

OFF until you set **Pause hours per day** in
[Configuration](Configuration.md). Then it turns ON during the worst hours
of each day, spread out so the device is never off longer than the limit
you set — across midnight too.

| Attribute | Meaning |
|---|---|
| `enabled` | False while pause hours is 0. |
| `hours_per_day` | How many hours are marked per day. |
| `max_consecutive_hours` | The longest unbroken pause allowed. |
| `next_pause` | Start of the next planned pause. |
| `pauses_today` / `pauses_tomorrow` | The full plan, as timestamps. |

Why this lives in SEMS instead of a template: taking "the N worst hours"
naively gives you one long block, because expensive hours cluster. See
[Example automations](Example-automations.md#5-pause-the-freezer-during-the-worst-hours).

## `sensor.sems_diagnostics` (debug mode only)

A **temporary verification aid**, created only while debug mode is enabled
in the options. The state is a plain-language health message, e.g.:

> `OK - 24h of prices, PV forecast peaks at 4600 W (95% of capacity)`

That percentage is worth a glance. Solar coverage is
`forecast ÷ installed capacity`, so if the forecast never gets near your
array, sunny hours quietly lose most of their discount and every score
flattens. A healthy summer figure is 60–90%; a dull winter day is
legitimately far lower. When it drops to a level the sun cannot explain
for the time of year, the state changes to `CHECK SETTINGS` and
`sanity_check` says what to look at — see
[the FAQ](FAQ.md#the-solar-forecast-looks-much-lower-than-what-my-panels-really-do).

The other attributes show where the data came from (`price_source`,
`pv_source`), the peak itself (`pv_peak_watts`,
`pv_peak_percent_of_capacity`), and an `hourly_overview`: one row per hour
with the PV forecast, the raw market price, the all-in price, the export
price, the effective price, the score and the rank. If a number ever looks
off, this is where you check what SEMS is actually working with — see
[Check that it works](Check-that-it-works.md).

Turn debug mode off via **Configure** once you trust the numbers — the
sensor disappears.

## Debug series sensors (debug mode only)

Three more temporary sensors, each showing one ingredient of the score so
you can chart and inspect them separately. The state is the value for the
current block; the `series` attribute holds one `{start, value}` entry
per block of the window:

| Entity | Shows |
|---|---|
| `sensor.sems_source_price` | The price exactly as read from your price entity, before any conversion — compare with the source integration. |
| `sensor.sems_effective_price` | What a kWh really costs you per block (the heart of the score). |
| `sensor.sems_pv_forecast` | The solar forecast SEMS is working with, in Watts per block. |
