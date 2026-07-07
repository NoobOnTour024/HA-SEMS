# How the score works

No formulas needed. Seven small steps, each a minute to read. If you
prefer playing over reading: the repository contains
[SEMS-simulator.xlsx-style examples](Dashboard-charts.md) and every number
below is visible per hour in the debug sensors.

## Step 1 — What does electricity really cost you?

Your energy app says: **€0.28 per kWh**. But that 28 cents is mostly
taxes. The build-up looks roughly like this:

| Part | Amount |
|---|---|
| Market price (what power costs "on the exchange") | €0.12 |
| Energy tax | €0.09 |
| Supplier markup | €0.02 |
| VAT over all of it | €0.05 |
| **What you pay ("all-in")** | **€0.28** |

Remember those two numbers: **you pay €0.28**, but **the market price
inside is only €0.12**.

## Step 2 — What does exporting solar power earn you?

When your panels produce more than you use, the surplus goes to the grid.
You do **not** get €0.28 for it. You get the **market price minus a
feed-in fee**:

> €0.12 − €0.02 = **€0.06 per kWh**

Taxes never come back. Selling earns €0.06; buying costs €0.28. That gap
is the whole secret of SEMS.

## Step 3 — Your own solar power is cheap, but not free

The sun is shining and your panels cover everything you use. Running the
dishwasher now — what does that cost?

- Not €0.28: you're not buying anything.
- Not €0.00 either: every kWh you use yourself, you could have *sold* for
  €0.06.

So using your own solar power costs you the **missed sales money: €0.06
per kWh**. SEMS calls this the **effective price** — what a kWh *really*
costs you that hour:

| Hour | Situation | Effective price |
|---|---|---|
| 03:00 (dark) | everything from the grid | €0.28 |
| 13:00 (full sun) | everything from your roof | €0.06 |
| 09:00 (some sun) | half and half | €0.17 |

This is why running appliances at noon is smart **even on a flat tariff**:
your contract price never changes, but the effective price does.

## Step 4 — How much of your usage does the sun cover?

For the blend in step 3, SEMS estimates per hour how much of your
consumption your panels cover. It uses your solar forecast and one
setting:

- **Solar installation size filled in** (e.g. 12 panels × 405 Wp = 4860):
  coverage = forecast ÷ installation size. A 600 W winter hour on a
  4860 Wp system covers ~12% — so that hour stays close to the grid
  price. Realistic.
- **Left at 0**: SEMS assumes the sunniest hour of the day covers your
  usage. Fine on sunny days, too optimistic on gloomy ones.

SEMS doesn't know what you will actually switch on — a 3000 W oven
changes everything. That inaccuracy is the price of keeping SEMS simple;
the numbers are a guide, not an invoice.

## Step 5 — From effective price to a score

Every block (hour, or quarter-hour if you chose that) gets points:

1. **Price points** — the block with the *lowest effective price* of the
   coming 24 hours gets the most; the most expensive gets zero.
2. **Sun points** — the *sunniest* block gets the most; a dark block gets
   zero.
3. **The balance slider mixes them.** At 100 only price points count, at
   0 only sun points, at 50 each counts half.

The result is the **score: 0 to 100**. One special case: is the all-in
price *negative* (below the free-power threshold)? Then you get **paid**
to use power. Such a block beats everything, so its score goes **above
100** — and `binary_sensor.sems_free_power` switches ON.

## Step 6 — Rank and relative score: the numbers you actually use

The raw score is the engine, but two friendlier views come out of it:

- **Rank** (`sensor.sems_rank`): all blocks of the coming 24 hours lined
  up from worst (1) to best (24 — or 96 in quarter mode). "Rank above 19"
  simply means: one of the 5 best hours of the day.
- **Relative score** (`sensor.sems_relative_score`): the same as a
  percentage. 0% = the worst block of the day, 100% = the best.

> ⚠️ **Relative score 100 does not mean "free".** Every day has exactly
> one best hour, so the relative score touches 100 every single day —
> also on an expensive day. It only ever compares hours *within* the
> coming 24 hours. Free power has its own signals: the free-power sensor
> turns ON, and the raw score (visible in charts) goes above 100.

## Step 7 — Appliances that need more than one hour

A dishwasher needs 2–3 hours, and the 3 best hours of the day are not
always next to each other. For that, SEMS also finds the best
*consecutive* run of 2, 3 and 4 hours:

- `binary_sensor.sems_best_2h_block` (and `3h`, `4h`) turns **ON** when
  the best run starts *now* — switch the appliance on at that moment.
- Its attributes always show when the best run is *planned*
  (`planned_start`, `planned_end`, `average_score`), so you can also
  automate on the clock.

Because SEMS re-plans every block (new prices can arrive), the planned
start can shift during the day — the attributes always show the current
plan.

## When data is missing

- Tomorrow's prices are usually published around 13:00 CET. Blocks whose
  prices are not known yet appear in `scores_24h` with empty (`null`)
  values — charts show a gap, automations see no rank for those blocks,
  and nothing is guessed.
- Fewer than 6 hours of price data (normally only when a source is
  broken)? SEMS marks its entities unavailable and writes a warning to
  the log, rather than pretending to know something it doesn't.
- No PV forecast (or no panels)? Sun points are zero everywhere and the
  effective price equals the all-in price — SEMS becomes a pure price
  optimizer.
