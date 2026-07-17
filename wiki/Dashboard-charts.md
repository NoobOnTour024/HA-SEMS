# Dashboard charts (ApexCharts)

Ready-to-paste dashboard cards for the excellent
[apexcharts-card](https://github.com/RomRider/apexcharts-card) (install it
via HACS → search "apexcharts"). **Every card on this page has been loaded
and tested in a real Home Assistant** — screenshots included.

All cards read one attribute: **`scores`** on `sensor.sems_rank`. It holds
**today and tomorrow** back to back (up to 48 hours), one entry per block:

```yaml
start, price, effective_price, pv, score, relative_score, rank
```

Because each day is ranked on its own, the `rank` line runs a fresh 1→24
for today and again for tomorrow (it resets at midnight). You get today's
earlier hours (a little history) on the left, and all of tomorrow once its
prices are published (~13:00 CET — before that the tomorrow half is
empty). One series per metric — no juggling two entities.

Copy a card, open your dashboard → **Edit** → **Add card** → **Manual**,
and paste.

## 1. Prices and rank

![Prices and rank](https://raw.githubusercontent.com/NoobOnTour024/HA-SEMS/main/assets/screenshots/card-prices-rank.png)

Blue = the all-in price you pay from the grid; green = the effective price
(what a kWh really costs you once your solar is counted, dips below zero on
sunny days); the orange step line is the rank, peaking at 24 on each day's
best hour.

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
  - entity: sensor.sems_rank
    name: All-in price
    unit: " €/kWh"
    type: column
    yaxis_id: price
    color: '#2a78d6'
    float_precision: 3
    data_generator: |
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(), r.price]);
  - entity: sensor.sems_rank
    name: Effective price
    unit: " €/kWh"
    type: column
    yaxis_id: price
    color: '#1baf7a'
    float_precision: 3
    data_generator: |
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(), r.effective_price]);
  - entity: sensor.sems_rank
    name: Rank (24 = best)
    unit: " "
    type: line
    yaxis_id: rank
    color: '#eda100'
    curve: stepline
    stroke_width: 3
    float_precision: 0
    data_generator: |
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(), r.rank]);
```

## 2. Price breakdown — what you pay vs what it really costs

![Price breakdown](https://raw.githubusercontent.com/NoobOnTour024/HA-SEMS/main/assets/screenshots/card-price-breakdown.png)

One stacked column per hour: the green part is the effective price, the
blue part on top is your solar advantage (the bit your panels let you
skip). Dark hours are almost all green; sunny hours have a small green
base — even below zero — and a big blue top.

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: SEMS — price breakdown
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
  - entity: sensor.sems_rank
    name: Effective price
    unit: " €/kWh"
    type: column
    color: '#1baf7a'
    float_precision: 3
    data_generator: |
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(), r.effective_price]);
  - entity: sensor.sems_rank
    name: Solar advantage
    unit: " €/kWh"
    type: column
    color: '#2a78d6'
    float_precision: 3
    data_generator: |
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(),
        r.price === null ? null : Math.round((r.price - r.effective_price) * 100000) / 100000]);
```

## 3. Score and sun

![Score and sun](https://raw.githubusercontent.com/NoobOnTour024/HA-SEMS/main/assets/screenshots/card-score-sun.png)

The score as columns (higher = better hour) with the solar forecast as a
soft area behind it — so you *see* why the score rises when the sun comes
out.

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
  - entity: sensor.sems_rank
    name: Score
    unit: " pts"
    type: column
    yaxis_id: score
    color: '#1baf7a'
    float_precision: 1
    data_generator: |
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(), r.score]);
  - entity: sensor.sems_rank
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
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(),
        r.pv === null ? null : r.pv / 1000]);
```

## 4. Appliance planner — rank with a top-5 line

![Appliance planner](https://raw.githubusercontent.com/NoobOnTour024/HA-SEMS/main/assets/screenshots/card-appliance-planner.png)

Just the rank, with a dashed line at 19.5: every column above it is a
**top-5 hour** of that day — where a "rank above 19" automation (see
[Example automations](Example-automations.md)) fires. Because each day is
ranked on its own, the line means the same thing on both days.

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
  - entity: sensor.sems_rank
    name: Rank (24 = best)
    unit: " "
    type: column
    color: '#2a78d6'
    float_precision: 0
    data_generator: |
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(), r.rank]);
```

> Using quarter-hour resolution? Rank runs 1–96; set the yaxis `max` to 96
> and the annotation `y` to ~77.5 (top-20 blocks ≈ top-5 hours).

## Rolling 24-hour view

Prefer one continuous window that always **starts at the current hour**
(no history, tail reaching into tomorrow morning)? Read the `scores_24h`
attribute of `sensor.sems_relative_score` instead of `scores` on
`sensor.sems_rank` — same fields, 24 forward-looking entries. To make the
axis shrink to exactly the known data, wrap the card in
[config-template-card](https://github.com/iantrich/config-template-card):

```yaml
type: custom:config-template-card
entities:
  - sensor.sems_relative_score
card:
  type: custom:apexcharts-card
  graph_span: >-
    ${ Math.ceil(new Date().getHours() + new Date().getMinutes()/60
       + states['sensor.sems_relative_score'].attributes.hours_available) + 'h' }
  # ... the rest of the card, series read attributes.scores_24h
```

## Good to know

- Everything refreshes at the start of each block (hour or quarter), and
  immediately when you move `number.sems_balance` — handy to see the
  effect of the slider live.
- Today's earlier hours are recomputed with your *current* settings;
  prices don't change retroactively, so they match what those hours were.
- Free-power hours push the score above 100 and the effective price below
  zero — both intentional, see
  [How the score works](How-the-score-works.md).
