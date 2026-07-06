# How the score works

No formulas needed to understand SEMS — the whole idea fits in one
question:

> **"What does one kWh really cost me this hour?"**

## The key insight: your own solar power is cheap, but not free

Say your all-in electricity price is **€0.28 per kWh**. That 28 cents is
mostly taxes; the bare market price inside it is only about **€0.12**.

Now the sun comes out and your panels cover everything you use.

- Using one kWh of your own solar power doesn't cost you 28 cents — you're
  not buying anything.
- But it isn't free either: you *could* have exported that kWh. Exporting
  earns the bare market price minus a feed-in fee: €0.12 − €0.02 =
  **€0.10**. By using it yourself, you give up those 10 cents.

So on this day, one kWh really costs you:

| Hour | What happens | Real cost per kWh |
|---|---|---|
| Dark hour (night) | You buy from the grid | **€0.28** |
| Sunny hour (noon) | You use your own power, miss the export payment | **€0.10** |
| Half-sunny hour | Half of each | **€0.19** |

SEMS calls this the **effective price**, and calculates it for every hour
of the coming 24. It's why running the dishwasher at noon is smart *even on
a flat tariff* — the price on your contract never changes, but the
effective price does, because of your panels.

## From effective price to score

For each hour in the window (the current hour + up to 23 hours ahead):

1. **Price points** — the hour with the lowest effective price in the
   window gets the maximum, the highest gets zero, everything else is in
   between.
2. **Sun points** — the sunniest hour of the window gets the maximum, a
   dark hour gets zero.
3. **The balance slider mixes them.** At balance 100 only the price points
   count, at 0 only the sun points, at 50 each counts half. The result is
   the **score: 0 to 100**.

### Why have a slider at all, if the effective price already knows about sun?

Because they answer different questions:

- **Balance 100** answers: *"when is consuming cheapest?"* — that's usually
  sunny hours, but during an extreme price spike it can actually be smarter
  to export your solar power (it earns a lot) and consume at night instead.
  The effective price captures that automatically.
- **Balance 0** answers: *"when do my panels produce?"* — pure
  self-consumption, prices ignored. Some people simply want this.
- In between blends the two.

## Free power (score above 100)

When the **all-in** price of an hour drops below the free-power threshold
(default: below €0.00), the score jumps **above 100** — the further below
zero, the higher. At −€0.05 the score is 105, at −€0.10 it's 110. These are
hours where you get *paid* to consume, so they beat every normal hour by
definition. `binary_sensor.sems_free_power` is ON during those hours.

Note: this looks at the price you *pay*, taxes included. A negative market
price alone isn't enough — after adding taxes the all-in price is often
still positive. That situation still shows up as a very low (even negative)
*effective* price and thus a high score, but it isn't "free".

## Rank and relative score

Two extra views on the same scores, because they're easier to automate on:

- **Rank** (`sensor.sems_rank`) — all hours in the window are sorted by
  score and numbered 1 (worst) to 24 (best). "Rank ≥ 20" always means "one
  of the 5 best hours of the coming day", no matter what the actual prices
  are. When two hours tie, the earlier hour gets the lower rank.
- **Relative score** (`sensor.sems_relative_score`) — the current hour as a
  percentage between the worst (0%) and best (100%) hour of the window.

## When data is missing

- Tomorrow's prices are usually published around 13:00 CET. Before that,
  the window is shorter than 24 hours; SEMS simply scores the hours it
  knows. The `hours_available` attribute tells you how many that is.
  Remember this for rank automations: with 18 known hours the best rank is
  18, not 24.
- With fewer than 6 hours of price data (normally only when a source is
  broken), SEMS marks its entities unavailable and writes a warning to the
  log, rather than pretending to know something it doesn't.
- No PV forecast (or no panels)? Sun points are zero everywhere and the
  effective price equals the all-in price — SEMS becomes a pure price
  optimizer.

## How much of my consumption does the sun cover?

That's the one thing SEMS has to estimate, because it doesn't know your
actual consumption. Two modes:

- **Solar installation size configured** (recommended): the coverage per
  hour is `forecast ÷ installation size`. A 600 W hour on a 5000 Wp system
  counts as covering ~12% — so on a gloomy winter day the effective price
  correctly stays close to the grid price, instead of pretending the whole
  day runs on solar.
- **Left at 0 (automatic)**: SEMS assumes the sunniest forecast hour of the
  day covers your consumption fully, and scales the other hours
  proportionally. Fine on sunny days, too optimistic on gloomy ones.

Either way, the balance slider's "follow the sun" side (balance towards 0)
keeps working on the *shape* of the solar day: the sunniest hour of a
gloomy day is still the sunniest hour.

## An honest limitation

Even with the installation size configured, SEMS still doesn't know what
you will actually *consume* in a given hour — running a 3000 W oven changes
the real coverage. That would require the kind of complexity (consumption
prediction) SEMS deliberately avoids. In practice this approximation points
at the right hours; the numbers are a guide, not an invoice.
