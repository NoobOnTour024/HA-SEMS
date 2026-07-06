# Dashboard charts (ApexCharts)

Ready-to-paste dashboard cards for the excellent
[apexcharts-card](https://github.com/RomRider/apexcharts-card) (install it
via HACS → search "apexcharts"). All cards read the `scores_24h` attribute
of `sensor.sems_relative_score`, which always covers the **coming** 24
hours — so these charts look forward, not back.

Copy a card, open your dashboard → **Edit** → **Add card** → **Manual**,
and paste.

## 1. Prices and rank — what will power cost, and when is it my moment?

The card you'll probably use most. Blue columns: the **all-in price** you
pay from the grid. Green columns in front of them: the **effective price**
— what a kWh *really* costs you once your solar production is taken into
account (see [How the score works](How-the-score-works.md)). The line is
the **rank**: touches 24 at the best hour of the day.

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: SEMS — prices and rank (next 24h)
graph_span: 24h
span:
  start: hour
apex_config:
  chart:
    stacked: false
  plotOptions:
    bar:
      columnWidth: 80%
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
    name: All-in price (€/kWh)
    type: column
    yaxis_id: price
    color: '#2a78d6'
    data_generator: |
      return entity.attributes.scores_24h.map((row) => {
        return [new Date(row.start).getTime(), row.price];
      });
  - entity: sensor.sems_relative_score
    name: Effective price (€/kWh)
    type: column
    yaxis_id: price
    color: '#1baf7a'
    data_generator: |
      return entity.attributes.scores_24h.map((row) => {
        return [new Date(row.start).getTime(), row.effective_price];
      });
  - entity: sensor.sems_relative_score
    name: Rank (24 = best hour)
    type: line
    yaxis_id: rank
    color: '#eda100'
    stroke_width: 3
    data_generator: |
      return entity.attributes.scores_24h.map((row) => {
        return [new Date(row.start).getTime(), row.rank];
      });
```

> ApexCharts draws the two price columns side by side per hour. Prefer
> truly overlapping bars? Use example 2 — same information, stacked so the
> full column height is the all-in price with the effective price inside
> it.

## 2. Price breakdown — overlapping view

One column per hour: the **total height is the all-in price**, the green
lower part is the **effective price**, and the blue upper part is your
**solar advantage** — the part of the price your panels let you skip. In
dark hours the column is almost entirely green: you pay the full price,
no advantage. In sunny hours the green base is small and the blue top is
large: most of the price disappears thanks to your own power.

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: SEMS — what you pay vs what it really costs
graph_span: 24h
span:
  start: hour
apex_config:
  chart:
    stacked: true
series:
  - entity: sensor.sems_relative_score
    name: Effective price (€/kWh)
    type: column
    color: '#1baf7a'
    data_generator: |
      return entity.attributes.scores_24h.map((row) => {
        return [new Date(row.start).getTime(), row.effective_price];
      });
  - entity: sensor.sems_relative_score
    name: Solar advantage (€/kWh)
    type: column
    color: '#2a78d6'
    data_generator: |
      return entity.attributes.scores_24h.map((row) => {
        return [new Date(row.start).getTime(),
                Math.round((row.price - row.effective_price) * 100000) / 100000];
      });
```

> During hours with a negative effective price the green part drops below
> the zero line — correct: consuming then is better than free.

## 3. Score and solar forecast

The score as columns (the higher, the better that hour) with the expected
solar production as a soft line behind it. Great for developing intuition:
you *see* why the score rises when the sun comes out.

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: SEMS — score and sun (next 24h)
graph_span: 24h
span:
  start: hour
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
    type: column
    yaxis_id: score
    color: '#1baf7a'
    data_generator: |
      return entity.attributes.scores_24h.map((row) => {
        return [new Date(row.start).getTime(), row.score];
      });
  - entity: sensor.sems_relative_score
    name: Solar forecast (kW)
    type: area
    yaxis_id: pv
    color: '#eda100'
    opacity: 0.25
    stroke_width: 2
    curve: smooth
    data_generator: |
      return entity.attributes.scores_24h.map((row) => {
        return [new Date(row.start).getTime(), row.pv / 1000];
      });
```

## 4. Appliance planner — rank with a top-5 line

Just the rank, with a marker line at 19.5: every column that pokes above
it is a **top-5 hour** of the coming day — the hours where a
"rank above 19" automation (see
[Example automations](Example-automations.md)) will fire.

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: SEMS — best hours for big appliances
graph_span: 24h
span:
  start: hour
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
    type: column
    color: '#2a78d6'
    data_generator: |
      return entity.attributes.scores_24h.map((row) => {
        return [new Date(row.start).getTime(), row.rank];
      });
```

## Good to know

- Everything refreshes at the top of each hour, and immediately when you
  move `number.sems_balance` — handy to see the effect of the slider live.
- Before ~13:00 CET only today's remaining hours are known
  (`hours_available` on `sensor.sems_relative_score`), so the charts show
  a shorter window in the morning. That's normal.
- Free-power hours can push the score above 100 and the effective price
  below zero — both are intentional, see
  [How the score works](How-the-score-works.md).
