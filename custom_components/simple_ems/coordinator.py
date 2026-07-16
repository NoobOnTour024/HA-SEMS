"""The SEMS data update coordinator.

This is the "engine room" of the integration. The coordinator:

1. Reads the hourly electricity prices from the configured price entity.
   Two source formats are supported (auto-detected, see the parser
   functions below):
     a. Attribute format — the entity carries ``raw_today`` /
        ``raw_tomorrow`` list attributes (old HACS Nord Pool integration,
        and several other price integrations use the same shape).
     b. Action format — the entity belongs to the core Nord Pool
        integration, which does NOT expose price attributes. SEMS then
        calls the ``nordpool.get_prices_for_date`` action for today and
        tomorrow. Those prices come back per MWh and possibly in
        15-minute blocks; SEMS converts to €/kWh and averages per hour.
2. Reads the hourly PV forecast (Watts) from the configured PV entity,
   if one is configured.
3. Converts prices to all-in consumer prices (or back to raw market
   prices) using the configured taxes, and derives the export price
   (raw market price minus the feed-in fee).
4. Feeds everything into the pure ``compute_scores`` function and stores
   the result so the sensor/binary_sensor/number entities can show it.

Recomputation happens at the start of every planning block (hour or
quarter-hour, depending on the resolution setting) and whenever one of
the source entities changes state.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from .calculator import compute_scores, find_best_block, to_all_in_price, to_raw_price
from .const import (
    BLOCK_DURATIONS_HOURS,
    CONF_ENERGY_TAX,
    CONF_EXPORT_FEE,
    CONF_PRICE_ENTITY,
    CONF_PRICE_FREE_THRESHOLD,
    CONF_PRICE_TYPE,
    CONF_PV_CAPACITY,
    CONF_PV_FORECAST_ENTITY,
    CONF_RESOLUTION,
    CONF_SUPPLIER_MARKUP,
    CONF_VAT_PERCENT,
    DEFAULT_BALANCE,
    DEFAULT_ENERGY_TAX,
    DEFAULT_EXPORT_FEE,
    DEFAULT_PRICE_FREE_THRESHOLD,
    DEFAULT_PRICE_TYPE,
    DEFAULT_PV_CAPACITY,
    DEFAULT_RESOLUTION,
    DEFAULT_SUPPLIER_MARKUP,
    DEFAULT_VAT_PERCENT,
    DOMAIN,
    MIN_HOURS_REQUIRED,
    PRICE_TYPE_RAW,
    RESOLUTION_QUARTER,
    WINDOW_HOURS,
)

_LOGGER = logging.getLogger(__name__)


def _hour_start(moment: datetime) -> datetime:
    """Return the start of the (local) hour that ``moment`` falls in."""
    return dt_util.as_local(moment).replace(minute=0, second=0, microsecond=0)


def _block_start(moment: datetime, minutes: int) -> datetime:
    """Return the start of the (local) time block that ``moment`` falls in.

    With ``minutes=60`` this is the top of the hour; with ``minutes=15``
    it is :00, :15, :30 or :45.
    """
    local = dt_util.as_local(moment)
    return local.replace(
        minute=(local.minute // minutes) * minutes, second=0, microsecond=0
    )


def _to_blocks(
    pairs: list[tuple[datetime, float]], minutes: int
) -> dict[datetime, float]:
    """Average (timestamp, value) pairs into one value per time block.

    Sources may deliver 15-minute values (the European market switched to
    15-minute intervals) or hourly values; this buckets them into whatever
    block size SEMS is configured to plan in, averaging where a block
    receives multiple values.
    """
    buckets: dict[datetime, list[float]] = {}
    for moment, value in pairs:
        buckets.setdefault(_block_start(moment, minutes), []).append(value)
    return {block: sum(values) / len(values) for block, values in buckets.items()}


def _to_hourly(pairs: list[tuple[datetime, float]]) -> dict[datetime, float]:
    """Average a list of (timestamp, value) pairs into one value per hour."""
    return _to_blocks(pairs, 60)


def _parse_datetime(value: Any) -> datetime | None:
    """Parse a datetime that may arrive as a datetime object or ISO string."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return dt_util.parse_datetime(value)
    return None


# ---------------------------------------------------------------------------
# Price parsing — kept in isolated functions so support for other source
# formats can be added later without touching the rest of the coordinator.
# ---------------------------------------------------------------------------


def _parse_price_attributes(state: State) -> list[tuple[datetime, float]]:
    """Parse hourly prices from the entity's attributes.

    Two attribute shapes are supported:

    * Nordpool-style ``raw_today`` / ``raw_tomorrow``: lists of dicts like
      ``{"start": <datetime>, "end": <datetime>, "value": <€/kWh>}``.
    * Frank Energie-style ``prices``: one list of dicts like
      ``{"from": <datetime>, "till": <datetime>, "price": <€/kWh>}``.

    The start key may be ``start`` or ``from`` and the price key may be
    ``value`` or ``price`` — all combinations are accepted. Returns an
    empty list when no such attributes exist (meaning: this is not an
    attribute-format entity).
    """
    pairs: list[tuple[datetime, float]] = []
    for attr in ("raw_today", "raw_tomorrow", "prices"):
        items = state.attributes.get(attr)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            start = _parse_datetime(item.get("start", item.get("from")))
            value = item.get("value", item.get("price"))
            if start is None or not isinstance(value, (int, float)):
                continue
            pairs.append((start, float(value)))
    return pairs


async def _fetch_nordpool_action_prices(
    hass: HomeAssistant, entity_id: str
) -> list[tuple[datetime, float]] | None:
    """Fetch prices via the core Nord Pool ``get_prices_for_date`` action.

    The core Nord Pool integration does not expose the full day of prices
    as attributes, so we call its action for today and tomorrow instead.
    The action returns prices per MWh, so they are divided by 1000 to get
    €/kWh. Tomorrow's prices simply do not exist before ~13:00 CET; that
    error is expected and silently skipped.

    Returns ``None`` when the entity does not belong to the core Nord Pool
    integration (meaning: try another format), or a list of pairs.
    """
    registry = er.async_get(hass)
    reg_entry = registry.async_get(entity_id)
    if reg_entry is None or reg_entry.platform != "nordpool" or not reg_entry.config_entry_id:
        return None

    today = dt_util.now().date()
    pairs: list[tuple[datetime, float]] = []
    for day in (today, today + timedelta(days=1)):
        try:
            response = await hass.services.async_call(
                "nordpool",
                "get_prices_for_date",
                {"config_entry": reg_entry.config_entry_id, "date": day.isoformat()},
                blocking=True,
                return_response=True,
            )
        except Exception as err:  # noqa: BLE001 - tomorrow is often not published yet
            _LOGGER.debug("No Nord Pool prices for %s (%s)", day, err)
            continue
        if not isinstance(response, dict):
            continue
        # The response is keyed by market area, e.g. {"NL": [ ... ]}. Some
        # versions wrap it one level deeper; unwrap until we find the list.
        for area_items in response.values():
            if isinstance(area_items, dict):
                area_items = next(iter(area_items.values()), [])
            if not isinstance(area_items, list):
                continue
            for item in area_items:
                if not isinstance(item, dict):
                    continue
                start = _parse_datetime(item.get("start"))
                price = item.get("price")
                if start is None or not isinstance(price, (int, float)):
                    continue
                # Nord Pool action prices are per MWh -> convert to per kWh.
                pairs.append((start, float(price) / 1000))
    return pairs


async def _fetch_energy_platform_forecast(
    hass: HomeAssistant, entity_id: str
) -> tuple[str, dict[datetime, float]] | None:
    """Fetch the hourly PV forecast the way the Energy dashboard does.

    Integrations like Forecast.Solar and Solcast do not necessarily expose
    their hourly forecast as entity attributes, but they DO provide it to
    Home Assistant's Energy dashboard through an official "energy" platform
    with an ``async_get_solar_forecast`` function. SEMS uses exactly that
    same route: it looks up which integration the selected PV entity
    belongs to and asks it for its solar forecast.

    The forecast comes back as ``{"wh_hours": {timestamp: watt_hours}}``.
    Watt-hours per (part of an) hour are summed per whole hour, which makes
    the number equal to the average power in Watts for that hour — exactly
    what the calculator expects.

    Returns ``None`` when the entity's integration does not offer a solar
    forecast (meaning: try something else), otherwise a
    (source_description, {hour_start: watts}) tuple.
    """
    registry = er.async_get(hass)
    reg_entry = registry.async_get(entity_id)
    if reg_entry is None or not reg_entry.config_entry_id:
        return None

    try:
        integration = await async_get_integration(hass, reg_entry.platform)
        energy_platform = await integration.async_get_platform("energy")
    except Exception:  # noqa: BLE001 - integration has no "energy" platform
        return None
    if not hasattr(energy_platform, "async_get_solar_forecast"):
        return None

    try:
        forecast = await energy_platform.async_get_solar_forecast(
            hass, reg_entry.config_entry_id
        )
    except Exception as err:  # noqa: BLE001 - never let a foreign integration crash SEMS
        _LOGGER.warning(
            "SEMS could not fetch the solar forecast from %s: %s",
            reg_entry.platform, err,
        )
        return None
    if not isinstance(forecast, dict) or not isinstance(forecast.get("wh_hours"), dict):
        return None

    hourly: dict[datetime, float] = {}
    for key, wh in forecast["wh_hours"].items():
        start = _parse_datetime(key)
        if start is None or not isinstance(wh, (int, float)):
            continue
        hour = _hour_start(start)
        hourly[hour] = hourly.get(hour, 0.0) + float(wh)
    if not hourly:
        return None
    return (f"solar forecast from the {reg_entry.platform} integration", hourly)


def _parse_pv_attributes(state: State) -> tuple[str, list[tuple[datetime, float]]]:
    """Parse an hourly PV forecast (Watts) from a forecast entity.

    Two common attribute shapes are supported:
    * Forecast.Solar-style: a ``watts`` dict of ``{timestamp: watts}``.
    * Solcast-style: a ``detailedForecast``/``forecast`` list of dicts with
      ``period_start`` and ``pv_estimate`` (in kW, converted to W).

    Returns a (format_description, pairs) tuple; pairs is empty when no
    known format was found.
    """
    watts = state.attributes.get("watts")
    if isinstance(watts, dict) and watts:
        pairs = []
        for key, value in watts.items():
            start = _parse_datetime(key)
            if start is not None and isinstance(value, (int, float)):
                pairs.append((start, float(value)))
        return ("watts attribute (Forecast.Solar)", pairs)

    for attr in ("detailedForecast", "detailedHourly", "forecast"):
        items = state.attributes.get(attr)
        if not isinstance(items, list) or not items:
            continue
        pairs = []
        for item in items:
            if not isinstance(item, dict):
                continue
            start = _parse_datetime(item.get("period_start", item.get("datetime")))
            estimate = item.get("pv_estimate", item.get("watts"))
            if start is None or not isinstance(estimate, (int, float)):
                continue
            # pv_estimate is in kW (Solcast); watts is already in W.
            factor = 1000.0 if "pv_estimate" in item else 1.0
            pairs.append((start, float(estimate) * factor))
        if pairs:
            return (f"{attr} attribute (Solcast-style)", pairs)

    return ("no known hourly forecast attribute found", [])


class SemsCoordinator(DataUpdateCoordinator[dict]):
    """Reads the source entities and recomputes all SEMS scores."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        # No fixed update_interval: updates are driven by the block clock
        # and by source entity changes (see async_setup). Recent Home
        # Assistant versions require passing the config entry explicitly.
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=None
        )
        self.entry = entry
        # The balance slider value lives here; the number entity restores it
        # after a restart and updates it when the user moves the slider.
        self.balance: int = DEFAULT_BALANCE
        self._unsubs: list = []

    # -- configuration helpers ------------------------------------------

    def _conf(self, key: str, default: Any) -> Any:
        """Read a setting, preferring options (editable) over initial data."""
        return self.entry.options.get(key, self.entry.data.get(key, default))

    @property
    def price_entity_id(self) -> str:
        return self.entry.data[CONF_PRICE_ENTITY]

    @property
    def pv_entity_id(self) -> str | None:
        return self.entry.data.get(CONF_PV_FORECAST_ENTITY) or None

    @property
    def free_threshold(self) -> float:
        return float(self._conf(CONF_PRICE_FREE_THRESHOLD, DEFAULT_PRICE_FREE_THRESHOLD))

    @property
    def block_minutes(self) -> int:
        """The planning block size in minutes: 60 (default) or 15."""
        resolution = self._conf(CONF_RESOLUTION, DEFAULT_RESOLUTION)
        return 15 if resolution == RESOLUTION_QUARTER else 60

    # -- lifecycle -------------------------------------------------------

    async def async_setup(self) -> None:
        """Start the block clock and watch the source entities."""
        # Recompute just after the start of every block (a few seconds late
        # so the price sensors have rolled over to the new block first).
        minutes = [0] if self.block_minutes == 60 else [0, 15, 30, 45]
        self._unsubs.append(
            async_track_time_change(
                self.hass, self._handle_hour_tick, minute=minutes, second=15
            )
        )
        watched = [self.price_entity_id]
        if self.pv_entity_id:
            watched.append(self.pv_entity_id)
        self._unsubs.append(
            async_track_state_change_event(self.hass, watched, self._handle_source_change)
        )

    def async_unload(self) -> None:
        """Stop all listeners (called when the config entry is unloaded)."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    async def _handle_hour_tick(self, _now: datetime) -> None:
        await self.async_request_refresh()

    async def _handle_source_change(self, _event: Event) -> None:
        await self.async_request_refresh()

    # -- the actual update ------------------------------------------------

    async def _async_update_data(self) -> dict:
        """Read sources, convert prices, compute scores. Never crash: raise
        UpdateFailed (entities become unavailable) when data is unusable."""
        # ---- 1. Get the hourly price series from the source entity ----
        state = self.hass.states.get(self.price_entity_id)
        if state is None:
            raise UpdateFailed(f"Price entity {self.price_entity_id} does not exist")

        pairs = _parse_price_attributes(state)
        price_source = "raw_today/raw_tomorrow attributes"
        if not pairs:
            action_pairs = await _fetch_nordpool_action_prices(self.hass, self.price_entity_id)
            if action_pairs:
                pairs = action_pairs
                price_source = "nordpool.get_prices_for_date action"
        if not pairs:
            _LOGGER.warning(
                "SEMS could not read hourly prices from %s: the entity has no "
                "raw_today/raw_tomorrow attributes and is not a core Nord Pool "
                "entity", self.price_entity_id,
            )
            raise UpdateFailed("No hourly prices found on the price entity")

        # ---- 2. Build the rolling window: current block + next blocks ----
        # A "block" is one hour (default) or one quarter-hour, depending on
        # the resolution setting. Sources with a coarser resolution than
        # the configured one (hourly prices + quarter-hour planning) simply
        # repeat their value for every block inside the hour.
        block_minutes = self.block_minutes
        blocks_per_hour = 60 // block_minutes
        window_blocks = WINDOW_HOURS * blocks_per_hour
        block_prices = _to_blocks(pairs, block_minutes)
        hourly_prices = _to_hourly(pairs)

        # Only contiguous blocks are used; the window stops at the first gap.
        now_block = _block_start(dt_util.now(), block_minutes)
        starts: list[datetime] = []
        source_prices: list[float] = []
        for i in range(window_blocks):
            block = now_block + timedelta(minutes=block_minutes * i)
            value = block_prices.get(block)
            if value is None:  # hourly source in quarter mode: use the hour's price
                value = hourly_prices.get(_hour_start(block))
            if value is None:
                break
            starts.append(block)
            source_prices.append(value)

        blocks_available = len(starts)
        hours_available = blocks_available / blocks_per_hour
        if blocks_available < MIN_HOURS_REQUIRED * blocks_per_hour:
            _LOGGER.warning(
                "SEMS has only %.2f hour(s) of price data (minimum is %d); "
                "marking entities unavailable", hours_available, MIN_HOURS_REQUIRED,
            )
            raise UpdateFailed(
                f"Only {hours_available:.2f} hours of price data available "
                f"(minimum {MIN_HOURS_REQUIRED})"
            )

        # ---- 3. Convert prices: all-in, raw market, and export price ----
        markup = float(self._conf(CONF_SUPPLIER_MARKUP, DEFAULT_SUPPLIER_MARKUP))
        tax = float(self._conf(CONF_ENERGY_TAX, DEFAULT_ENERGY_TAX))
        vat = float(self._conf(CONF_VAT_PERCENT, DEFAULT_VAT_PERCENT))
        export_fee = float(self._conf(CONF_EXPORT_FEE, DEFAULT_EXPORT_FEE))
        price_type = self._conf(CONF_PRICE_TYPE, DEFAULT_PRICE_TYPE)

        if price_type == PRICE_TYPE_RAW:
            # The source delivers bare market prices: add taxes to get the
            # all-in price the consumer pays.
            raw_prices = source_prices
            all_in_prices = [to_all_in_price(p, markup, tax, vat) for p in raw_prices]
        else:
            # The source already delivers all-in prices: estimate the bare
            # market price by stripping the taxes off again (needed to know
            # what exporting earns).
            all_in_prices = source_prices
            raw_prices = [to_raw_price(p, markup, tax, vat) for p in all_in_prices]

        # Exporting earns the bare market price minus the feed-in fee.
        export_prices = [p - export_fee for p in raw_prices]

        # Plausibility check on the price-type setting. SEMS reads whatever
        # entity the user picked; integrations like Frank Energie offer
        # several price sensors (market, market+vat, all-in) that all look
        # alike. A Dutch all-in price averages roughly €0.20-0.35/kWh while
        # bare market prices average far lower — a mismatch here means the
        # scores would be silently wrong, so flag it in the diagnostics.
        average_all_in = sum(all_in_prices) / len(all_in_prices)
        if price_type != PRICE_TYPE_RAW and average_all_in < 0.10:
            sanity_check = (
                f"The average source price (€{average_all_in:.3f}/kWh) looks like a "
                "bare market price, but the price type is set to all-in. Did you "
                "pick the all-in sensor of your price integration — or should the "
                "price type be raw?"
            )
        elif price_type == PRICE_TYPE_RAW and average_all_in > 0.45:
            sanity_check = (
                f"After adding taxes the average price is €{average_all_in:.3f}/kWh, "
                "which is unusually high. Your source may already include taxes — "
                "consider the all-in price type, or check that you picked the "
                "market-price sensor."
            )
        else:
            sanity_check = "OK"

        # ---- 4. Get the PV forecast, aligned to the same blocks ----
        # Two routes, tried in order:
        #   a. hourly attributes on the entity itself (watts dict,
        #      Solcast-style forecast lists),
        #   b. the integration's official solar forecast — the same data
        #      the Energy dashboard shows. This is how core Forecast.Solar
        #      works: its entities carry no hourly attributes at all.
        # Forecasts are hourly; in quarter-hour mode every block inside an
        # hour gets that hour's forecast.
        pv_watts = [0.0] * blocks_available
        pv_source = "no PV entity configured"
        hourly_pv: dict[datetime, float] = {}
        if self.pv_entity_id:
            pv_state = self.hass.states.get(self.pv_entity_id)
            if pv_state is None:
                pv_source = f"PV entity {self.pv_entity_id} does not exist"
                _LOGGER.warning("SEMS: %s; treating PV as 0 W", pv_source)
            else:
                pv_source, pv_pairs = _parse_pv_attributes(pv_state)
                if pv_pairs:
                    hourly_pv = _to_hourly(pv_pairs)
                else:
                    energy_forecast = await _fetch_energy_platform_forecast(
                        self.hass, self.pv_entity_id
                    )
                    if energy_forecast is not None:
                        pv_source, hourly_pv = energy_forecast
                if not hourly_pv:
                    _LOGGER.warning(
                        "SEMS could not read an hourly PV forecast from %s "
                        "(%s); treating PV as 0 W", self.pv_entity_id, pv_source,
                    )
            pv_watts = [hourly_pv.get(_hour_start(block), 0.0) for block in starts]

        # ---- 5. Compute the scores (pure function, unit-tested) ----
        pv_capacity = float(self._conf(CONF_PV_CAPACITY, DEFAULT_PV_CAPACITY))
        scores = compute_scores(
            all_in_prices,
            export_prices,
            pv_watts,
            self.balance,
            self.free_threshold,
            pv_capacity,
        )
        for entry, start in zip(scores, starts):
            entry["start"] = start.isoformat()

        current = scores[0]

        # Blocks whose prices are not published yet (typically tomorrow,
        # before ~13:00 CET) get explicit empty entries: score None means
        # "unknown", so charts show a gap instead of pretending to know.
        for i in range(blocks_available, window_blocks):
            block = now_block + timedelta(minutes=block_minutes * i)
            scores.append(
                {
                    "start": block.isoformat(),
                    "price": None,
                    "export_price": None,
                    "effective_price": None,
                    "pv": None,
                    "score": None,
                    "relative_score": None,
                    "rank": None,
                }
            )

        # ---- 6. Best consecutive blocks for slow appliances ----
        # For each duration (e.g. 2h dishwasher): the start moment of the
        # best-scoring consecutive run within the known data.
        score_values = [s["score"] for s in scores[:blocks_available]]
        best_blocks: dict[str, dict | None] = {}
        for duration_hours in BLOCK_DURATIONS_HOURS:
            length = duration_hours * blocks_per_hour
            index = find_best_block(score_values, length)
            if index is None:
                best_blocks[f"{duration_hours}h"] = None
                continue
            average = sum(score_values[index : index + length]) / length
            best_blocks[f"{duration_hours}h"] = {
                "start": starts[index].isoformat(),
                "end": (starts[index] + timedelta(hours=duration_hours)).isoformat(),
                "average_score": round(average, 1),
                # True while the best run starts in the current block: the
                # moment to switch the appliance on.
                "starts_now": index == 0,
            }

        # ---- 6b. Per-calendar-day rankings (today and tomorrow) ----
        # The rolling window above mixes today and tomorrow, so its rank
        # scale would grow past 24 if it were extended. Instead we ALSO
        # score each calendar day on its own: ranks stay 1..24 within the
        # day, and the whole of today plus the whole of tomorrow (once its
        # prices are published) is available for charts and per-day
        # automations. Each day includes all its known blocks, so today
        # also holds the hours that already passed.
        def _score_day(day_start: datetime) -> list[dict]:
            day_end = day_start + timedelta(days=1)
            day_starts: list[datetime] = []
            day_sources: list[float] = []
            block = day_start
            while block < day_end:
                value = block_prices.get(block)
                if value is None:  # hourly source in quarter mode
                    value = hourly_prices.get(_hour_start(block))
                if value is not None:
                    day_starts.append(block)
                    day_sources.append(value)
                block += timedelta(minutes=block_minutes)
            if not day_starts:
                return []
            if price_type == PRICE_TYPE_RAW:
                day_raw = day_sources
                day_all_in = [to_all_in_price(p, markup, tax, vat) for p in day_raw]
            else:
                day_all_in = day_sources
                day_raw = [to_raw_price(p, markup, tax, vat) for p in day_all_in]
            day_export = [p - export_fee for p in day_raw]
            day_pv = [hourly_pv.get(_hour_start(b), 0.0) for b in day_starts]
            day_scores = compute_scores(
                day_all_in, day_export, day_pv, self.balance,
                self.free_threshold, pv_capacity,
            )
            for entry, start in zip(day_scores, day_starts):
                entry["start"] = start.isoformat()
            return day_scores

        today_midnight = dt_util.as_local(dt_util.now()).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_scores = _score_day(today_midnight)
        tomorrow_scores = _score_day(today_midnight + timedelta(days=1))

        # The rank of the block we are in now WITHIN today. This is what
        # sensor.sems_rank reports: a stable 1..24 scale all day long. The
        # rolling window's own rank is not used for it, because its scale
        # shrinks to hours_available (only 14 before tomorrow publishes),
        # which made "rank above 19" impossible in the morning.
        current_rank_today = next(
            (s["rank"] for s in today_scores if s["start"] == current["start"]),
            None,
        )
        today_hours = len(today_scores) / blocks_per_hour

        # ---- 7. Package everything for the entities ----
        return {
            "scores": scores,
            "current": current,
            "today": today_scores,
            "tomorrow": tomorrow_scores,
            "current_rank_today": current_rank_today,
            "today_hours": round(today_hours, 2),
            "hours_available": round(hours_available, 2),
            "blocks_available": blocks_available,
            "blocks_per_hour": blocks_per_hour,
            "block_minutes": block_minutes,
            "best_blocks": best_blocks,
            # The free-power flag is deliberately derived from the all-in
            # price itself, NOT from the score.
            "free_power": current["price"] < self.free_threshold,
            "balance": self.balance,
            # Verification / diagnostics info (shown by the debug sensors).
            "price_source": price_source,
            "pv_source": pv_source,
            "price_type": price_type,
            "pv_capacity": pv_capacity,
            "sanity_check": sanity_check,
            "source_prices": [round(p, 5) for p in source_prices],
            "raw_prices": [round(p, 5) for p in raw_prices],
            "all_in_prices": [round(p, 5) for p in all_in_prices],
            "export_prices": [round(p, 5) for p in export_prices],
            "pv_watts": [round(w, 1) for w in pv_watts],
            "window_start": starts[0].isoformat(),
            "last_computed": dt_util.now().isoformat(),
        }
