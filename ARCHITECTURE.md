# SEMS — Architecture & design decisions

This file is the durable source of truth for **how SEMS is built and why**.
It is meant for maintainers (and for an AI assistant resuming work after a
context reset): read it before changing the integration, and update it when
a design decision changes.

It contains design/technical information only — no credentials or personal
data. Operational details (the local test rig, release chores) live outside
this repository.

---

## 1. Purpose & philosophy

SEMS (Simple Energy Management System) is a HACS-installable Home Assistant
custom integration. Every block (hour, or quarter-hour) it scores the coming
day(s) on how attractive it is to use electricity, from **dynamic prices**
and a **solar forecast**.

- **Simple over clever.** 80% efficient and understandable beats 95% and
  complex. No ML, no battery logic, no export control, no consumption
  prediction.
- **Reads, never fetches.** SEMS does not call the internet. It reads two
  entities the user already has (a price sensor and, optionally, a PV
  forecast sensor) and does maths. The one exception is the core Nord Pool
  case (see §4), where it calls that integration's own action.
- **Works out of the box.** Only the two source entities are required;
  every other setting has a sensible default (Dutch 2026 tax values).

## 2. Repository & distribution

- GitHub: `NoobOnTour024/HA-SEMS` (public). Wiki is the user documentation;
  the `wiki/` folder in the repo is the source and is mirrored to the
  GitHub Wiki.
- Integration domain: **`simple_ems`** (the folder is
  `custom_components/simple_ems/`). It was renamed from `sems` because that
  domain collided with the GoodWe SEMS integration in the HA brands repo,
  which made HACS show the wrong logo. Entity ids stay `sensor.sems_*`
  because the device is named "SEMS".
- HACS installs by **release tag**, so every user-visible change needs a new
  version in `manifest.json` and a GitHub release.
- Icon ships inside the integration at `custom_components/simple_ems/brand/`
  (`icon.png` 256, `icon@2x.png` 512). Home Assistant picks it up from
  **2026.3.0** onward; the HA brands repo no longer accepts custom-
  integration icons.

## 3. Data flow (the coordinator)

`coordinator.py` holds a `DataUpdateCoordinator` that recomputes at the
start of every block and whenever a source entity changes. Per update it:

1. Reads the price series from the price entity (see §4).
2. Builds the rolling window (current block + following blocks, up to 24h),
   stopping at the first gap.
3. Converts prices to all-in / raw / export (see §6).
4. Reads the PV forecast (see §5), aligned to the blocks.
5. Runs the pure `compute_scores` (see §7) for the rolling window, for
   **today** (whole calendar day) and for **tomorrow** (whole calendar
   day), and finds the best consecutive blocks for slow appliances.
6. Packages everything into `coordinator.data` for the entities.

The coordinator is created with `config_entry=entry` — recent HA versions
require this or setup raises "Detected code that relies on ContextVar".

## 4. Price handling (`_parse_price_attributes`, `_fetch_nordpool_action_prices`)

Auto-detected, isolated in parser functions so more formats can be added:

- **Attribute formats**: `raw_today` / `raw_tomorrow` (Nord Pool HACS,
  EnergyZero, …) with items `{start|from, value|price}`, and Frank
  Energie's `prices` (a single list of `{from, till, price}`). Start key
  may be `start` or `from`; price key `value` or `price`.
- **Core Nord Pool** has no price attributes: SEMS finds the entity's
  config entry and calls the `nordpool.get_prices_for_date` action for
  today and tomorrow. Those prices are **per MWh → divide by 1000**, and
  may be 15-minute blocks.
- Values are bucketed into the configured block size (hour or quarter),
  averaging where several source values fall in one block.

## 5. PV forecast handling (`_parse_pv_attributes`, `_fetch_energy_platform_forecast`)

Optional. Tried in order:

1. Hourly attributes on the entity — a `watts` dict (Forecast.Solar-style)
   or a Solcast-style `forecast`/`detailedForecast` list (`pv_estimate` is
   kW → ×1000).
2. Otherwise, the integration's **official solar forecast** — the same data
   the Energy dashboard uses. SEMS looks up the entity's integration and
   calls its `energy` platform's `async_get_solar_forecast`, which returns
   `{"wh_hours": {timestamp: Wh}}`. Wh summed per hour ≈ average W. This is
   how core **Forecast.Solar** works (its entities carry no hourly
   attributes) — the user just picks any of its sensors.

No PV entity → all PV treated as 0; SEMS becomes a pure price optimiser.

## 6. Price type & taxes

- `price_type` = `all_in` (default) or `raw`. The tax fields (supplier
  markup, energy tax, VAT) are shown for **both** types:
  - `raw`: taxes are **added** → all-in = (raw + markup + tax) × (1+VAT%).
  - `all_in`: taxes are used **in reverse** (`to_raw_price`) to estimate the
    bare market price hiding in the all-in price — needed to know what
    exporting earns.
- `export_fee` (feed-in cost). Exporting earns `raw market price − fee`.
- The coordinator runs a **sanity check**: if the average price is
  implausible for the chosen type (all-in < €0.10, or raw giving > €0.45
  all-in), the diagnostics state becomes `CHECK SETTINGS …`. Guards against
  picking the wrong sensor of integrations like Frank Energie.

## 7. The scoring algorithm — the "effective price" model

Pure, unit-tested, no HA imports: `calculator.py`
(`compute_scores`, `to_all_in_price`, `to_raw_price`, `find_best_block`).

The core idea — **what does one kWh really cost you this block?**

- A dark block: the full all-in price (you buy from the grid).
- A sunny block: only the missed export payment (you consume your own
  power that you could have sold for `market − fee`).
- Blend by **solar coverage**: `forecast ÷ installed Wp` (capped at 1), or
  if capacity is 0, `forecast ÷ the day's sunniest block`.

`effective = (1 − coverage) × all_in + coverage × export_price`.

Then per block: `base_price` (1 = cheapest effective in the window, 0 =
dearest), `base_pv` (1 = sunniest), combined by the **balance** slider
(100 = only price, 0 = only sun, 50 = both). Score 0–100; a block whose
**all-in** price is below the free threshold scores **> 100** ("free
power"). Ranks 1..N (1 = worst) by score, ties broken chronologically.
`relative_score` stretches score to 0–100 within the window.

> This replaced the original spec's separate "arbitration points" (user-
> approved): those assumed exporting earns the full price, which is wrong.
> The effective-price model captures the same intent honestly and even
> handles price spikes (exporting can beat self-consumption then).

## 8. Time resolution (blocks)

Setting `resolution` = `hour` (default, 24 blocks/day) or `quarter_hour`
(96/day). Hour blocks suit devices that can't switch fast (heat pumps).
Sources coarser than the setting repeat their value per block; finer
sources are averaged. `block_minutes` and `blocks_per_hour` flow through
`coordinator.data`.

## 9. Scoring windows: rolling vs per-calendar-day

Two framings coexist deliberately:

- **Rolling window** (current block + next, up to 24h): drives
  `sensor.sems_relative_score` (its `scores_24h` attribute), the best-block
  sensors and `free_power`. Its rank scale would grow past 24 if extended,
  and it shrinks in the morning (`hours_available` < 24 before tomorrow's
  prices publish ~13:00 CET).
- **Per calendar day** (00:00–23:59, all known blocks incl. past ones):
  drives the rank entity. Ranks are always a stable 1..24 (1..96) and reset
  at midnight. This is what charts and per-day automations should use.

**History note:** `sensor.sems_rank` used the rolling window until v0.4.0,
which made "rank above 19" impossible in the morning (scale only reached
`hours_available`, e.g. 14 at 10:00). Since v0.4.0 it ranks within **today**.

## 10. Entities (the contract)

Always present:

- `sensor.sems_relative_score` — **main sensor**. State 0–100 (current
  block vs the rolling window). Attribute `scores_24h`: the rolling window,
  one entry per block `{start, price, effective_price, pv, score,
  relative_score, rank}`, with `null` entries for not-yet-published blocks.
  Also `best_blocks`, `hours_available`, `block_minutes`.
- `sensor.sems_rank` — the current block's rank **within today** (1..24 /
  1..96). Attribute `scores`: **today + tomorrow** (up to 48h / 192 blocks),
  each block with its per-day `rank` and a real timestamp (so charts reset
  the rank at midnight); plus `best_hour_today`, `best_hour_tomorrow`,
  `current_rank`, `hours_available`, `ranked_within`. (This subsumes the
  former `sems_rank_today` / `sems_rank_tomorrow`, removed in v0.5.0.)
- `sensor.sems_current_price` — current all-in price (verify the tax
  conversion). Attrs: price_type, export_price, effective_price.
- `sensor.sems_score` — raw score of the current block (0–100, >100 = free).
  **Disabled by default** (easily confused with relative_score).
- `binary_sensor.sems_free_power` — ON when current all-in price < free
  threshold. Derived from price, never from score.
- `binary_sensor.sems_best_2h_block` / `_3h_block` / `_4h_block` — ON when
  the best consecutive run of that length starts now. Attrs:
  `planned_start`, `planned_end`, `average_score`.
- `number.sems_balance` — 0–100 slider (default 50). Survives restarts;
  recomputes on change.

Debug mode (`debug_mode`, default ON so non-developers can verify):

- `sensor.sems_diagnostics` — plain-language health string + `hourly_overview`
  (per-block raw/all-in/export/effective price, pv, score, rank), sources,
  `sanity_check`.
- `sensor.sems_source_price` / `sems_effective_price` / `sems_pv_forecast` —
  one series each (state = current block, `series` attribute = per block).

Plus `diagnostics.py`: a **Download diagnostics** button dumping settings,
everything computed, and the raw source-entity attributes (no secrets) — so
a user's exact situation can be replayed.

## 11. Home Assistant constraints & gotchas

- **Recorder attribute limit = 16384 bytes** (`MAX_STATE_ATTRS_BYTES`).
  Above it HA logs a warning and does **not** store the attributes. A block
  costs ~139 bytes, so a 48h `scores` in quarter mode (~192 blocks ≈ 26 KB)
  would exceed it. Fix: large forecast attributes (`scores`, `scores_24h`)
  are declared `_unrecorded_attributes` — the live value stays for charts/
  automations, it just isn't written to the database. This also avoids
  needlessly recording forecast data (which is never looked back at).
- Pass `config_entry=` to `DataUpdateCoordinator` (see §3).
- Brand icon: see §2.

## 12. Testing & CI

- `tests/test_calculator.py` — pure `compute_scores` / `to_*` /
  `find_best_block` (no HA needed). `tests/test_config_flow.py` — drives the
  setup/options flow against a real HA core (needs
  `pytest-homeassistant-custom-component`, runs in CI).
- CI (`.github/workflows/ci.yml`): **hassfest**, **HACS validation**, and
  the tests. Keep it green before releasing.
- Manual/visual verification is done on a local HA test rig (not in this
  repo). Screenshots for the wiki/README come from there.

## 13. Working agreement

- After a context reset (`/clear`, `/compact`), **read this file before
  making changes** to SEMS.
- Keep this file current when a design decision changes.
- Keep secrets and personal/operational notes out of it.
