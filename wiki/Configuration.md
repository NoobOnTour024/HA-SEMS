# Configuration

SEMS is configured entirely through the UI. During setup you get two
screens; afterwards you can change everything (except the source entities)
via **Settings → Devices & services → SEMS → Configure**.

**The golden rule: only the two source entities are required. Every other
setting has a default that works.**

## Screen 1 — Source entities

### Electricity price entity (required)

The sensor that knows your hourly electricity prices. SEMS understands two
formats and detects the right one automatically:

1. **Sensors with `raw_today` / `raw_tomorrow` attributes** — the classic
   format used by the HACS Nord Pool integration and several supplier
   integrations. Open your price sensor in **Developer tools → States**; if
   you see those attributes, you're set.
2. **The core Nord Pool integration** — this one has no price attributes.
   SEMS recognises it and asks Nord Pool for today's and tomorrow's prices
   through its built-in `get_prices_for_date` action. Prices arrive per MWh
   and sometimes per 15 minutes; SEMS converts them to €/kWh per hour
   automatically. You don't have to do anything — just pick your Nord Pool
   price sensor.

### PV forecast entity (optional)

Pick **any sensor of your solar forecast integration** — for example
Forecast.Solar's *Estimated energy production - today*. SEMS finds the
hourly forecast in one of two ways, automatically:

1. **Hourly attributes on the entity itself** — some integrations put the
   hourly forecast in attributes (a `watts` dict, or a Solcast-style
   `forecast` list). If your entity has those, SEMS reads them directly.
2. **The Energy dashboard route** — core **Forecast.Solar** entities carry
   no hourly attributes at all. That's fine: the hourly data exists inside
   the integration (the Energy dashboard shows it), and SEMS asks for it
   through the same official mechanism the Energy dashboard uses. It only
   needs to know *which* integration to ask — which is why picking any one
   of its sensors is enough. This also works for Solcast and any other
   integration that can show a solar forecast on the Energy dashboard.

The diagnostics sensor tells you which route was used (`pv_source`).

No solar panels? Leave it empty. SEMS then treats all solar values as 0 and
the score is driven by price alone.

## Screen 2 — Settings

### Price type

The most important setting. Ask yourself: *does my price sensor show what I
actually pay per kWh, or the bare market price?*

- **All-in** (default) — the sensor's price already includes energy tax and
  VAT. Most supplier integrations (EnergyZero, Zonneplan, Frank Energie)
  work like this. SEMS uses the price unchanged.
- **Raw** — the sensor shows the bare market/spot price. The core Nord Pool
  integration works like this. SEMS adds your taxes on top:

  ```
  all-in price = (raw price + supplier markup + energy tax) × (1 + VAT%)
  ```

Not sure? Compare your sensor's current value with the price on your energy
supplier's app or invoice. Around €0.25–0.35 → all-in. Around €0.05–0.15 →
raw.

You can always verify the result: `sensor.sems_current_price` shows the
all-in price SEMS calculated for this hour. It should match what your
supplier's app says you pay right now.

### Planning resolution

- **Hour blocks** (default) — 24 blocks per day. Best for devices that
  cannot switch quickly, like heat pumps.
- **Quarter-hour blocks** — 96 blocks per day, following the 15-minute
  prices some suppliers already use. Rank then runs 1–96, `scores_24h`
  holds 96 entries, and everything recomputes every quarter.

Sources with hourly prices work fine in quarter mode (each quarter gets
its hour's price), and 15-minute sources work fine in hour mode (SEMS
averages them). Pick what fits your devices.

### Export fee (feed-in costs)

What your supplier charges per exported kWh ("terugleverkosten"), default
€0.02/kWh. **Enter it as a positive number** — SEMS subtracts it for you.
Exporting one kWh earns you: `bare market price − export fee`. This number
is at the heart of the score — see
[How the score works](How-the-score-works.md).

### Solar installation size (0 = automatic)

The total rated power of your solar panels in Watts — count:
number of panels × Wp per panel, e.g. 12 × 405 Wp = **4860** (also on your
installer's invoice).

SEMS uses it to estimate how much of your consumption your own solar power
covers each hour: a forecast of 600 W on a 4860 Wp system clearly covers
very little, so that hour is priced close to the normal grid price.

**About efficiency:** real installations rarely reach their rated maximum
(panel temperature, orientation, inverter limits). You do *not* need to
correct for that — just enter the rated total. The forecast itself already
predicts realistic output, so the estimate errs slightly on the careful
side. Only if your system structurally peaks far below its rating (e.g. an
east-west roof, heavy shading) can you enter a lower value — roughly your
real summer peak — to give sunny hours a bit more weight.

Left at **0** (the default), SEMS assumes the sunniest forecast hour of the
day covers your consumption. That works fine on sunny days but is too
optimistic on gloomy winter days — filling in your real installation size
makes those days realistic too. See
[How the score works](How-the-score-works.md).

### Free power threshold

Default €0.00. When the **all-in** price of the current hour drops *below*
this value, power counts as free: the score jumps above 100 and
`binary_sensor.sems_free_power` switches ON. Leave it at 0.00 unless you
want to be more or less strict about what "free" means.

### Debug mode

ON by default after installation. Adds `sensor.sems_diagnostics`, which
shows exactly what data SEMS found and every intermediate number. Turn it
off via Configure once you've verified your setup — see
[Check that it works](Check-that-it-works.md).

## Screen 3 — Taxes and markup

This screen appears for **every** price type, because the values do two
different jobs:

- **Raw market prices**: SEMS *adds* them on top of the market price to
  calculate what you actually pay per kWh.
- **All-in prices**: SEMS uses them *in reverse* — it strips them off your
  all-in price to estimate the bare market price hiding inside it. That
  market price determines what **exporting** your solar power earns
  (exported power never earns the taxes back), which sits at the heart of
  the score.

So even with an all-in contract it pays to fill these in accurately —
grab your energy contract or last invoice. Enter all amounts **as positive
numbers**:

- **Supplier markup** — what your supplier charges per kWh on top of the
  market price (default €0.020/kWh excl. VAT).
- **Energy tax** — the Dutch "energiebelasting" (default €0.0916/kWh
  excl. VAT, the 2026 value).
- **VAT** — default 21%.

> ⚠️ **The defaults are Dutch 2026 values and work fine to start with —
> but check them against your own contract.** Every supplier charges a
> different markup, and tax rates change every year.

## The balance slider (not in the config — it's an entity!)

`number.sems_balance` lives on your dashboard, not in the settings, because
it's meant to be played with:

- **100** — only the (effective) price matters. Cheapest hours win.
- **0** — only solar self-consumption matters. Sunniest hours win.
- **50** (default) — both matter equally.

Moving the slider recalculates all scores immediately, so you can see the
effect right away in a chart. See
[Check that it works](Check-that-it-works.md) for a ready-made chart card.
