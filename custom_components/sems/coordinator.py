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

Recomputation happens at the top of every hour and whenever one of the
source entities changes state.
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
from homeassistant.util import dt as dt_util

from .calculator import compute_scores, to_all_in_price, to_raw_price
from .const import (
    CONF_ENERGY_TAX,
    CONF_EXPORT_FEE,
    CONF_PRICE_ENTITY,
    CONF_PRICE_FREE_THRESHOLD,
    CONF_PRICE_TYPE,
    CONF_PV_CAPACITY,
    CONF_PV_FORECAST_ENTITY,
    CONF_SUPPLIER_MARKUP,
    CONF_VAT_PERCENT,
    DEFAULT_BALANCE,
    DEFAULT_ENERGY_TAX,
    DEFAULT_EXPORT_FEE,
    DEFAULT_PRICE_FREE_THRESHOLD,
    DEFAULT_PRICE_TYPE,
    DEFAULT_PV_CAPACITY,
    DEFAULT_SUPPLIER_MARKUP,
    DEFAULT_VAT_PERCENT,
    DOMAIN,
    MIN_HOURS_REQUIRED,
    PRICE_TYPE_RAW,
    WINDOW_HOURS,
)

_LOGGER = logging.getLogger(__name__)


def _hour_start(moment: datetime) -> datetime:
    """Return the start of the (local) hour that ``moment`` falls in."""
    return dt_util.as_local(moment).replace(minute=0, second=0, microsecond=0)


def _to_hourly(pairs: list[tuple[datetime, float]]) -> dict[datetime, float]:
    """Average a list of (timestamp, value) pairs into one value per hour.

    Price sources may deliver 15-minute values (the European market
    switched to 15-minute intervals); SEMS works with hourly averages.
    Sources that already deliver hourly values pass through unchanged.
    """
    buckets: dict[datetime, list[float]] = {}
    for moment, value in pairs:
        buckets.setdefault(_hour_start(moment), []).append(value)
    return {hour: sum(values) / len(values) for hour, values in buckets.items()}


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
    """Parse Nordpool-style ``raw_today`` / ``raw_tomorrow`` attributes.

    Each attribute is a list of dicts like
    ``{"start": <datetime>, "end": <datetime>, "value": <€/kWh>}``.
    Some integrations name the price key ``price`` instead of ``value``;
    both are accepted. Returns an empty list when the attributes are absent
    (meaning: this is not an attribute-format entity).
    """
    pairs: list[tuple[datetime, float]] = []
    for attr in ("raw_today", "raw_tomorrow"):
        items = state.attributes.get(attr)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            start = _parse_datetime(item.get("start"))
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
        # No fixed update_interval: updates are driven by the top-of-hour
        # clock and by source entity changes (see async_setup).
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None)
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

    # -- lifecycle -------------------------------------------------------

    async def async_setup(self) -> None:
        """Start the hourly clock and watch the source entities."""
        # Recompute just after the top of every hour (a few seconds late so
        # the price sensors have rolled over to the new hour first).
        self._unsubs.append(
            async_track_time_change(self.hass, self._handle_hour_tick, minute=0, second=15)
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

        hourly_prices = _to_hourly(pairs)

        # ---- 2. Build the rolling window: current hour + next hours ----
        # Only contiguous hours are used; the window stops at the first gap.
        now_hour = _hour_start(dt_util.now())
        starts: list[datetime] = []
        source_prices: list[float] = []
        for i in range(WINDOW_HOURS):
            hour = now_hour + timedelta(hours=i)
            if hour not in hourly_prices:
                break
            starts.append(hour)
            source_prices.append(hourly_prices[hour])

        hours_available = len(starts)
        if hours_available < MIN_HOURS_REQUIRED:
            _LOGGER.warning(
                "SEMS has only %d hour(s) of price data (minimum is %d); "
                "marking entities unavailable", hours_available, MIN_HOURS_REQUIRED,
            )
            raise UpdateFailed(
                f"Only {hours_available} hours of price data available "
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

        # ---- 4. Get the PV forecast, aligned to the same hours ----
        pv_watts = [0.0] * hours_available
        pv_source = "no PV entity configured"
        if self.pv_entity_id:
            pv_state = self.hass.states.get(self.pv_entity_id)
            if pv_state is None:
                pv_source = f"PV entity {self.pv_entity_id} does not exist"
                _LOGGER.warning("SEMS: %s; treating PV as 0 W", pv_source)
            else:
                pv_source, pv_pairs = _parse_pv_attributes(pv_state)
                hourly_pv = _to_hourly(pv_pairs)
                pv_watts = [hourly_pv.get(hour, 0.0) for hour in starts]
                if not pv_pairs:
                    _LOGGER.warning(
                        "SEMS could not read an hourly PV forecast from %s "
                        "(%s); treating PV as 0 W", self.pv_entity_id, pv_source,
                    )

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

        # ---- 6. Package everything for the entities ----
        return {
            "scores": scores,
            "current": current,
            "hours_available": hours_available,
            # The free-power flag is deliberately derived from the all-in
            # price itself, NOT from the score.
            "free_power": current["price"] < self.free_threshold,
            "balance": self.balance,
            # Verification / diagnostics info (shown by the debug sensor).
            "price_source": price_source,
            "pv_source": pv_source,
            "price_type": price_type,
            "pv_capacity": pv_capacity,
            "raw_prices": [round(p, 5) for p in raw_prices],
            "all_in_prices": [round(p, 5) for p in all_in_prices],
            "export_prices": [round(p, 5) for p in export_prices],
            "pv_watts": [round(w, 1) for w in pv_watts],
            "window_start": starts[0].isoformat(),
            "last_computed": dt_util.now().isoformat(),
        }
