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

## Screen 2 — Prices and taxes

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

### Supplier markup, energy tax, VAT

Only *added* to the price when price type is **Raw** — but they matter for
everyone: SEMS also uses them in reverse to estimate the bare market price
inside an all-in price, which it needs to know what **exporting** earns
(exported power never earns the taxes back).

> ⚠️ **The defaults are Dutch 2026 values**: supplier markup €0.020/kWh,
> energy tax €0.0916/kWh (both excl. VAT), VAT 21%. **Check them against
> your own contract** — every supplier charges a different markup, and tax
> rates change every year.

### Export fee (feed-in costs)

What your supplier charges per exported kWh ("terugleverkosten"), default
€0.02/kWh. Exporting one kWh earns you:
`bare market price − export fee`. This number is at the heart of the score —
see [How the score works](How-the-score-works.md).

### Solar installation size (0 = automatic)

The total peak power of your solar panels in Watts — e.g. **5000** for a
5 kWp system (usually on your installer's invoice, or count:
number of panels × Wp per panel).

SEMS uses it to estimate how much of your consumption your own solar power
covers each hour: a forecast of 600 W on a 5000 Wp system clearly covers
very little, so that hour is priced close to the normal grid price.

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

## The balance slider (not in the config — it's an entity!)

`number.sems_balance` lives on your dashboard, not in the settings, because
it's meant to be played with:

- **100** — only the (effective) price matters. Cheapest hours win.
- **0** — only solar self-consumption matters. Sunniest hours win.
- **50** (default) — both matter equally.

Moving the slider recalculates all scores immediately, so you can see the
effect right away in a chart. See
[Check that it works](Check-that-it-works.md) for a ready-made chart card.
