# Dashboard charts (ApexCharts)

Ready-to-paste dashboard cards for the excellent
[apexcharts-card](https://github.com/RomRider/apexcharts-card) (install it
via HACS → search "apexcharts"). **Every card on this page has been loaded
and tested in a real Home Assistant** — screenshots included.

All cards read the `scores_24h` attribute of `sensor.sems_relative_score`
and span **48 hours starting at midnight** — today and tomorrow in full —
with a dashed *now* line marking the current moment. So in the evening
you always see the whole of tomorrow the moment its prices are published.
Prefer a shorter axis? Change `graph_span` to `24h` or `36h` — one line
per card. Or let the axis
[shrink to the known data](#advanced-an-axis-that-shrinks-to-the-known-data)
automatically with the recipe below.

Two things to know:

- **SEMS looks forward.** The data starts at the current block and
  reaches at most 24 hours ahead, so the chart is empty before the *now*
  line and beyond the end of the window. Want yesterday's history too?
  See the tip at the bottom.
- **Unknown blocks show as gaps.** Before ~13:00 CET tomorrow's prices are
  not published yet; those blocks are `null` in `scores_24h` and simply
  show nothing. The gap fills in by itself once the prices arrive.

Copy a card, open your dashboard → **Edit** → **Add card** → **Manual**,
and paste.

## 1. Prices and rank — what will power cost, and when is it my moment?

![Prices and rank](https://raw.githubusercontent.com/NoobOnTour024/HA-SEMS/main/assets/screenshots/card-prices-rank.png)

Blue columns: the **all-in price** you pay from the grid. Green columns:
the **effective price** — what a kWh *really* costs you once your solar
production is taken into account (it dives below zero on sunny days — see
[How the score works](How-the-score-works.md)). The orange step line is
the **rank**: it touches 24 at the best hour of the day.

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: SEMS — prices and rank
graph_span: 48h
span:
  start: day
now:
  show: true
  label: now
yaxis:
  - id: price
    decimals: 2
  - id: rank
    opposite: true
    min: 0
    max: 24
    decimals: 0
series:
  - entity: sensor.sems_relative_score
    name: All-in price
    unit: " €/kWh"
    type: column
    yaxis_id: price
    color: '#2a78d6'
    float_precision: 3
    data_generator: |
      return entity.attributes.scores_24h.map((row) => {
        return [new Date(row.start).getTime(), row.price];
      });
  - entity: sensor.sems_relative_score
    name: Effective price
    unit: " €/kWh"
    type: column
    yaxis_id: price
    color: '#1baf7a'
    float_precision: 3
    data_generator: |
      return entity.attributes.scores_24h.map((row) => {
        return [new Date(row.start).getTime(), row.effective_price];
      });
  - entity: sensor.sems_relative_score
    name: Rank (24 = best)
    unit: " "
    type: line
    yaxis_id: rank
    color: '#eda100'
    curve: stepline
    stroke_width: 3
    float_precision: 0
    data_generator: |
      return entity.attributes.scores_24h.map((row) => {
        return [new Date(row.start).getTime(), row.rank];
      });
```

## 2. Price breakdown — overlapping view

![Price breakdown](https://raw.githubusercontent.com/NoobOnTour024/HA-SEMS/main/assets/screenshots/card-price-breakdown.png)

One column per hour: the **total height is the all-in price**, the green
lower part is the **effective price**, and the blue top is your **solar
advantage** — the part of the price your panels let you skip. In dark
hours the column is almost entirely green: you pay the full price, no
advantage. In sunny hours the green base is small (it can even drop below
zero) and the blue top is large.

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: SEMS — what you pay vs what it really costs
graph_span: 48h
span:
  start: day
now:
  show: true
  label: now
apex_config:
  chart:
    stacked: true
series:
  - entity: sensor.sems_relative_score
    name: Effective price
    unit: " €/kWh"
    type: column
    color: '#1baf7a'
    float_precision: 3
    data_generator: |
      return entity.attributes.scores_24h.map((row) => {
        return [new Date(row.start).getTime(), row.effective_price];
      });
  - entity: sensor.sems_relative_score
    name: Solar advantage
    unit: " €/kWh"
    type: column
    color: '#2a78d6'
    float_precision: 3
    data_generator: |
      return entity.attributes.scores_24h.map((row) => {
        return [new Date(row.start).getTime(),
                row.price === null ? null :
                Math.round((row.price - row.effective_price) * 100000) / 100000];
      });
```

## 3. Score and solar forecast

![Score and sun](https://raw.githubusercontent.com/NoobOnTour024/HA-SEMS/main/assets/screenshots/card-score-sun.png)

The score as columns (the higher, the better that hour) with the expected
solar production as a soft area behind it. Great for developing intuition:
you *see* why the score rises when the sun comes out. Free-power hours
poke above the 100 line.

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: SEMS — score and sun
graph_span: 48h
span:
  start: day
now:
  show: true
  label: now
yaxis:
  - id: score
    min: 0
    decimals: 0
  - id: pv
    opposite: true
    min: 0
    decimals: 1
series:
  - entity: sensor.sems_relative_score
    name: Score
    unit: " pts"
    type: column
    yaxis_id: score
    color: '#1baf7a'
    float_precision: 1
    data_generator: |
      return entity.attributes.scores_24h.map((row) => {
        return [new Date(row.start).getTime(), row.score];
      });
  - entity: sensor.sems_relative_score
    name: Solar forecast
    unit: " kW"
    type: area
    yaxis_id: pv
    color: '#eda100'
    opacity: 0.25
    stroke_width: 2
    curve: smooth
    float_precision: 1
    data_generator: |
      return entity.attributes.scores_24h.map((row) => {
        return [new Date(row.start).getTime(),
                row.pv === null ? null : row.pv / 1000];
      });
```

## 4. Appliance planner — rank with a top-5 line

![Appliance planner](https://raw.githubusercontent.com/NoobOnTour024/HA-SEMS/main/assets/screenshots/card-appliance-planner.png)

Just the rank, with a dashed marker line at 19.5: every column that pokes
above it is a **top-5 hour** of the coming day — the hours where a
"rank above 19" automation (see
[Example automations](Example-automations.md)) will fire.

> Using quarter-hour resolution? Rank runs 1–96 there; change the yaxis
> `max` to 96 and the annotation `y` to e.g. 77.5 (top-20 blocks ≈ top-5
> hours).

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: SEMS — best hours for big appliances
graph_span: 48h
span:
  start: day
now:
  show: true
  label: now
yaxis:
  - min: 0
    max: 24
    decimals: 0
apex_config:
  annotations:
    yaxis:
      - y: 19.5
        borderColor: '#1baf7a'
        strokeDashArray: 4
        label:
          text: top-5 hours
          style:
            color: '#ffffff'
            background: '#1baf7a'
series:
  - entity: sensor.sems_relative_score
    name: Rank (24 = best)
    unit: " "
    type: column
    color: '#2a78d6'
    float_precision: 0
    data_generator: |
      return entity.attributes.scores_24h.map((row) => {
        return [new Date(row.start).getTime(), row.rank];
      });
```

## Advanced: an axis that shrinks to the known data

A 48-hour axis always shows everything, but the part where prices are not
published yet is inevitably empty. ApexCharts itself cannot resize its
time axis to the data — but the small helper card
[config-template-card](https://github.com/iantrich/config-template-card)
(HACS → search "config template card") can compute the span live, so the
axis ends **exactly at the last known price block**: ~24 hours wide in the
morning, growing to ~45 hours in the evening once tomorrow is published.
Tested like everything on this page.

Wrap any card from this page like this — paste the full card under
`card:` and replace only its `graph_span` line with the template:

```yaml
type: custom:config-template-card
entities:
  - sensor.sems_relative_score
card:
  type: custom:apexcharts-card
  graph_span: >-
    ${ Math.ceil(new Date().getHours() + new Date().getMinutes()/60
       + states['sensor.sems_relative_score'].attributes.hours_available) + 'h' }
  # ... the rest of the card, unchanged (span, now, series, ...)
```

The template adds "hours since midnight" to SEMS's `hours_available`, so
the span always runs from midnight to the end of the known window and the
chart re-fits automatically whenever new prices arrive.

## Good to know

- Everything refreshes at the start of each block (hour or quarter), and
  immediately when you move `number.sems_balance` — handy to see the
  effect of the slider live.
- Want to see the **past hours of today** as well? Add a series without a
  `data_generator`: apexcharts-card then charts the recorded history of
  the sensor itself, e.g. `entity: sensor.sems_relative_score` with
  `group_by: {func: avg, duration: 1h}`. SEMS's own attribute data always
  looks forward.
- Free-power hours can push the score above 100 and the effective price
  below zero — both are intentional, see
  [How the score works](How-the-score-works.md).
