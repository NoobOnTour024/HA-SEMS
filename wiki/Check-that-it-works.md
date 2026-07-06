# Check that it works

You don't need to read code to verify SEMS — everything it calculates is
visible in Home Assistant. This page is a 5-minute checklist.

## Step 1 — Read the diagnostics sensor

Debug mode is ON after installation, so you have `sensor.sems_diagnostics`.
Open **Developer tools → States** and look it up.

**The state should say something like:**

> `OK - 24h of prices, PV forecast found`

What to check:

| You see | It means |
|---|---|
| `24h of prices` (or 13–23h before ~13:00) | Prices are being read correctly. |
| `PV forecast found` | Your solar forecast is being read. |
| `no PV data (treated as 0 W)` | Fine if you configured no PV entity; a problem if you did. |
| The sensor is `unavailable` | Fewer than 6 hours of prices found — check your price entity and the Home Assistant log (search for "SEMS"). |

Now open the sensor's **attributes**. You'll see, hour by hour:

- `raw_prices` — the bare market prices,
- `all_in_prices` — after tax conversion (what you pay),
- `export_prices` — what exporting earns (market price minus fee),
- `pv_watts` — the solar forecast,
- `price_source` / `pv_source` — which format SEMS detected.

## Step 2 — Verify one price by hand

Open your energy supplier's app and compare the current price with
`sensor.sems_current_price`. They should match (within a rounding cent).
If not, the [price type setting](Configuration.md) is probably wrong —
that's the #1 setup mistake, and exactly what this sensor exists for.

## Step 3 — Sanity-check the scores

Look at `sensor.sems_score` → attribute `scores_24h`, or put the chart
below on a dashboard. Ask yourself:

- On a day with cheap sunny afternoon hours: are those hours scoring
  highest? They should.
- Are the most expensive dark evening hours scoring lowest? They should.
- Move `number.sems_balance` to 0: do the scores now follow the sun shape?
  Move it to 100: do they follow the (effective) price? Changes apply
  immediately.

## A dashboard card to see everything (ApexCharts)

Install [apexcharts-card](https://github.com/RomRider/apexcharts-card) via
HACS, then add this card to a dashboard:

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: SEMS — score for the next 24h
graph_span: 24h
span:
  start: hour
series:
  - entity: sensor.sems_score
    name: Score
    type: column
    data_generator: |
      return entity.attributes.scores_24h.map((row) => {
        return [new Date(row.start).getTime(), row.score];
      });
  - entity: sensor.sems_score
    name: Price (ct/kWh)
    type: line
    color: gray
    data_generator: |
      return entity.attributes.scores_24h.map((row) => {
        return [new Date(row.start).getTime(), row.price * 100];
      });
```

Green tall columns = good hours. The gray line shows the all-in price so
you can see *why* an hour scores the way it does.

## Step 4 — Watch it for a day

- At the top of each hour the score, rank and relative score change.
- Shortly after ~13:00 CET, `hours_available` should jump to 24 (tomorrow's
  prices arrived).
- If your prices ever go negative: the score jumps above 100 and
  `binary_sensor.sems_free_power` turns ON.

## All good? Turn off debug mode

Go to **Settings → Devices & services → SEMS → Configure** and switch
**Debug mode** off. The diagnostics sensor disappears; everything else
keeps working. You can switch it back on any time something looks odd.

## Something's wrong?

- Check **Settings → System → Logs** and search for `sems` — SEMS logs a
  clear warning whenever it can't read something.
- The [FAQ](FAQ.md) covers the common cases.
