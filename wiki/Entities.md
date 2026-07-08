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

The current block's rank within the window: **1 = worst, 24 = best** (or
**1–96** with quarter-hour resolution). Ranks are unique — no two blocks
share a rank. Great for automations: "rank above 19" always means "one of
the 5 best hours of the coming day".

Attribute `hours_available`: with fewer than 24 known hours, the best
possible rank is lower too (e.g. 18 when 18 hours are known).

This sensor uses a **rolling** window (now + the next hours), so in the
evening it already looks into tomorrow morning. For a clean per-calendar-
day view, use the two sensors below instead.

## `sensor.sems_rank_today` and `sensor.sems_rank_tomorrow`

Each of these ranks **one whole calendar day on its own**, so the rank is
always **1 (worst) … 24 (best)** for that day — no matter the time, and no
matter how much of tomorrow is known. `sems_rank_today` covers all of
today (including the hours that already passed); `sems_rank_tomorrow` is
`unavailable` until tomorrow's prices are published (typically after
~13:00 CET), then covers all of tomorrow.

- **State**: that day's **best hour**, as `HH:MM` (e.g. `13:00`) — a
  glanceable "run big things around this time".
- **Attribute `scores`**: one entry per block of the day, each with
  `start`, `price`, `effective_price`, `pv`, `score`, `relative_score` and
  `rank` (1–24 within the day). This is what charts and per-day
  automations read — e.g. *"tomorrow's rank-24 hour"*.
- Attributes `best_hour`, `worst_hour`, `hours_available`.

Because each day is self-contained, plotting both sensors' `scores` gives
a two-day chart where the rank resets to a fresh 1–24 at midnight — see
[Dashboard charts](Dashboard-charts.md). Example: start the boiler in
tomorrow's single best hour:

```yaml
automation:
  - alias: "Boiler in tomorrow's best hour"
    trigger:
      - platform: time_pattern
        minutes: 0
    condition:
      - condition: template
        value_template: >
          {% set s = state_attr('sensor.sems_rank_tomorrow', 'scores') %}
          {% if s %}
            {% set best = (s | sort(attribute='rank') | last) %}
            {{ as_datetime(best.start) == now().replace(minute=0, second=0, microsecond=0) }}
          {% else %}false{% endif %}
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.boiler
```

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
