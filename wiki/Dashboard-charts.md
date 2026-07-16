# Dashboard charts (ApexCharts)

Ready-to-paste dashboard cards for the excellent
[apexcharts-card](https://github.com/RomRider/apexcharts-card) (install it
via HACS → search "apexcharts"). **Every card on this page has been loaded
and tested in a real Home Assistant** — screenshots included.

All cards below read the two **per-calendar-day** sensors,
`sensor.sems_rank_today` and `sensor.sems_rank_tomorrow`. That gives you:

- **The whole of today, including the hours that already passed** (a bit of
  history on the left of the chart), plus **all of tomorrow** once its
  prices are published (~13:00 CET — before that the tomorrow half is
  simply empty).
- **A clean 1–24 rank per day** that resets at midnight, instead of one
  scale stretched across two days.

Each sensor exposes its day in the `scores` attribute — one entry per
block with `start`, `price`, `effective_price`, `pv`, `score`,
`relative_score` and `rank`. The cards just plot two series per metric
(one per day).

Copy a card, open your dashboard → **Edit** → **Add card** → **Manual**,
and paste.

> Prefer a single **rolling** 24-hour axis that always starts at the
> current hour (no history)? See
> [Rolling 24-hour view](#rolling-24-hour-view) at the bottom.

## 1. Prices and rank

![Rank per day](https://raw.githubusercontent.com/NoobOnTour024/HA-SEMS/main/assets/screenshots/card-rank-per-day.png)

All-in price columns (dark = today, light = tomorrow) with each day's rank
as a step line that runs a fresh 1→24 (dark orange today, light orange
tomorrow). The rank line peaks at 24 on each day's best hour.

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: SEMS — rank per day (today + tomorrow)
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
  - entity: sensor.sems_rank_today
    name: All-in price (today)
    unit: " €/kWh"
    type: column
    yaxis_id: price
    color: '#2a78d6'
    float_precision: 3
    data_generator: |
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(), r.price]);
  - entity: sensor.sems_rank_tomorrow
    name: All-in price (tomorrow)
    unit: " €/kWh"
    type: column
    yaxis_id: price
    color: '#85b7eb'
    float_precision: 3
    data_generator: |
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(), r.price]);
  - entity: sensor.sems_rank_today
    name: Rank today (24 = best)
    unit: " "
    type: line
    yaxis_id: rank
    color: '#eda100'
    curve: stepline
    stroke_width: 3
    float_precision: 0
    data_generator: |
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(), r.rank]);
  - entity: sensor.sems_rank_tomorrow
    name: Rank tomorrow (24 = best)
    unit: " "
    type: line
    yaxis_id: rank
    color: '#efc35a'
    curve: stepline
    stroke_width: 3
    float_precision: 0
    data_generator: |
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(), r.rank]);
```

## 2. Price breakdown — what you pay vs what it really costs

![Price breakdown](https://raw.githubusercontent.com/NoobOnTour024/HA-SEMS/main/assets/screenshots/card-price-breakdown.png)

One stacked column per hour: the green part is the **effective price**
(what a kWh really costs you that hour), the blue part on top is your
**solar advantage** (the bit your panels let you skip). Dark hours are
almost all green; sunny hours have a small green base — even below zero —
and a big blue top.

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: SEMS — price breakdown (today + tomorrow)
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
  - entity: sensor.sems_rank_today
    name: Effective price (today)
    unit: " €/kWh"
    type: column
    color: '#1baf7a'
    float_precision: 3
    data_generator: |
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(), r.effective_price]);
  - entity: sensor.sems_rank_today
    name: Solar advantage (today)
    unit: " €/kWh"
    type: column
    color: '#2a78d6'
    float_precision: 3
    data_generator: |
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(),
        r.price === null ? null : Math.round((r.price - r.effective_price) * 100000) / 100000]);
  - entity: sensor.sems_rank_tomorrow
    name: Effective price (tomorrow)
    unit: " €/kWh"
    type: column
    color: '#1baf7a'
    float_precision: 3
    data_generator: |
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(), r.effective_price]);
  - entity: sensor.sems_rank_tomorrow
    name: Solar advantage (tomorrow)
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
out. Today is the darker pair, tomorrow the lighter pair.

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: SEMS — score and sun (today + tomorrow)
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
  - entity: sensor.sems_rank_today
    name: Score (today)
    unit: " pts"
    type: column
    yaxis_id: score
    color: '#1baf7a'
    float_precision: 1
    data_generator: |
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(), r.score]);
  - entity: sensor.sems_rank_tomorrow
    name: Score (tomorrow)
    unit: " pts"
    type: column
    yaxis_id: score
    color: '#9fe1cb'
    float_precision: 1
    data_generator: |
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(), r.score]);
  - entity: sensor.sems_rank_today
    name: Solar (today)
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
  - entity: sensor.sems_rank_tomorrow
    name: Solar (tomorrow)
    unit: " kW"
    type: area
    yaxis_id: pv
    color: '#efc35a'
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

Just the rank for both days, with a dashed line at 19.5: every column
above it is a **top-5 hour** of that day — where a "rank above 19"
automation (see [Example automations](Example-automations.md)) fires.
Because each day is ranked on its own, the line means the same thing on
both days.

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
  - entity: sensor.sems_rank_today
    name: Rank today
    unit: " "
    type: column
    color: '#2a78d6'
    float_precision: 0
    data_generator: |
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(), r.rank]);
  - entity: sensor.sems_rank_tomorrow
    name: Rank tomorrow
    unit: " "
    type: column
    color: '#85b7eb'
    float_precision: 0
    data_generator: |
      return entity.attributes.scores.map((r) => [new Date(r.start).getTime(), r.rank]);
```

## Rolling 24-hour view

If you'd rather see one continuous window that always **starts at the
current hour** (no history, tail reaching into tomorrow morning), use the
`scores_24h` attribute of `sensor.sems_relative_score` instead of the
per-day sensors. It holds 24 forward-looking entries with the same fields
(`price`, `effective_price`, `pv`, `score`, `rank`). Swap the two series
in card 1 for a single series like:

```yaml
  - entity: sensor.sems_relative_score
    name: All-in price
    unit: " €/kWh"
    type: column
    yaxis_id: price
    float_precision: 3
    data_generator: |
      return entity.attributes.scores_24h.map((r) => [new Date(r.start).getTime(), r.price]);
```

The window reaches at most 24 hours ahead, so the axis is empty before
*now* and past the end of the window. To make the axis shrink to exactly
the known data, wrap the card in
[config-template-card](https://github.com/iantrich/config-template-card)
and compute `graph_span` from `hours_available`:

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

## Good to know

- Everything refreshes at the start of each block (hour or quarter), and
  immediately when you move `number.sems_balance` — handy to see the
  effect of the slider live.
- The per-day history (today's earlier hours) is recomputed with your
  *current* settings; prices don't change retroactively, so it matches
  what those hours actually were.
- Free-power hours push the score above 100 and the effective price below
  zero — both intentional, see
  [How the score works](How-the-score-works.md).
