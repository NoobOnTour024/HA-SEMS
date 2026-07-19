"""The SEMS sensors.

Five sensors are created (the last one only when debug mode is on):

* ``sensor.sems_relative_score`` — 0–100%, current block vs the rolling 24h
                                   window. Carries that window in the
                                   ``scores_24h`` attribute.
* ``sensor.sems_rank``           — 1..24, rank of the current block within
                                   today. Its ``scores`` attribute carries
                                   today + tomorrow (per-day ranks) — the
                                   main attribute for charts and per-day
                                   automations.
* ``sensor.sems_current_price``  — the converted all-in price of the current
                                   hour, so users can verify the tax math.
* ``sensor.sems_score``          — the raw internal score of the current
                                   hour. Advanced: disabled by default,
                                   because it is easily confused with the
                                   relative score (see the class docstring).
* ``sensor.sems_diagnostics``    — TEMPORARY verification aid (debug mode):
                                   a plain-language health message with all
                                   intermediate numbers as attributes.

In debug mode three extra series sensors are created so every input and
result can be charted and inspected separately:

* ``sensor.sems_source_price``    — the price exactly as read from the
                                    source entity, per block.
* ``sensor.sems_effective_price`` — what a kWh really costs per block.
* ``sensor.sems_pv_forecast``     — the solar forecast per block.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEBUG_MODE, DEFAULT_DEBUG_MODE, DOMAIN
from .coordinator import SemsCoordinator

# Unique-id suffixes of sensors that older versions created but this one no
# longer does. They are removed on setup so they don't linger as
# "unavailable" after an update.
_REMOVED_SUFFIXES = ("_rank_today", "_rank_tomorrow")


def _remove_stale_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete entities from removed sensors (merged into sensor.sems_rank)."""
    registry = er.async_get(hass)
    for suffix in _REMOVED_SUFFIXES:
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}{suffix}"
        )
        if entity_id:
            registry.async_remove(entity_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the SEMS sensors for this config entry."""
    coordinator: SemsCoordinator = hass.data[DOMAIN][entry.entry_id]
    _remove_stale_entities(hass, entry)

    entities: list[SensorEntity] = [
        SemsScoreSensor(coordinator, entry),
        SemsRelativeScoreSensor(coordinator, entry),
        SemsRankSensor(coordinator, entry),
        SemsCurrentPriceSensor(coordinator, entry),
    ]
    # The diagnostics and series sensors are temporary verification aids;
    # they only exist while debug mode is enabled in the options.
    debug = entry.options.get(CONF_DEBUG_MODE, entry.data.get(CONF_DEBUG_MODE, DEFAULT_DEBUG_MODE))
    if debug:
        entities.append(SemsDiagnosticsSensor(coordinator, entry))
        entities.append(SemsSourcePriceSensor(coordinator, entry))
        entities.append(SemsEffectivePriceSensor(coordinator, entry))
        entities.append(SemsPvForecastSensor(coordinator, entry))

    async_add_entities(entities)


def _round(value: float | None, digits: int) -> float | None:
    """Round a value, passing None (= data not published yet) through."""
    return None if value is None else round(value, digits)


class SemsSensorBase(CoordinatorEntity[SemsCoordinator], SensorEntity):
    """Common plumbing for all SEMS sensors: device grouping and naming.

    ``_attr_has_entity_name`` combined with the device name "SEMS" makes
    Home Assistant generate entity ids like ``sensor.sems_score``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: SemsCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="SEMS",
            manufacturer="SEMS",
            model="Simple Energy Management System",
        )


class SemsScoreSensor(SemsSensorBase):
    """The raw internal score of the current hour (0–100, >100 = free power).

    Advanced sensor, DISABLED by default: the raw score is easily confused
    with the relative score (both are relative to the 24h window; the
    relative score is simply the raw score stretched to exactly 0–100).
    Enable it via the entity settings if you want to automate on it. The
    per-hour raw scores stay available to everyone in the ``scores_24h``
    attribute of the relative score sensor.
    """

    _attr_name = "Score"
    _attr_icon = "mdi:speedometer"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: SemsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "score")

    @property
    def native_value(self) -> float | None:
        return round(self.coordinator.data["current"]["score"], 1)


class SemsRelativeScoreSensor(SemsSensorBase):
    """Current hour relative to the 24h window: 0 = worst, 100 = best.

    This is the main SEMS sensor: its ``scores_24h`` attribute carries the
    full window (one entry per hour) for automations and dashboard charts.
    Note that 100 means "the best hour of the coming day", NOT "free power"
    — free power is signalled by ``binary_sensor.sems_free_power`` and by
    raw scores above 100 inside ``scores_24h``.
    """

    _attr_name = "Relative score"
    _attr_icon = "mdi:percent"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    # scores_24h is a large forecast blob (up to ~13 KB in quarter mode).
    # Keep it out of the database: it is a forecast (never looked back at)
    # and would risk the recorder's 16 KB attribute limit. The live value
    # stays available for charts and automations.
    _unrecorded_attributes = frozenset({"scores_24h"})

    def __init__(self, coordinator: SemsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "relative_score")

    @property
    def native_value(self) -> float | None:
        return round(self.coordinator.data["current"]["relative_score"], 1)

    @property
    def extra_state_attributes(self) -> dict:
        """Expose the full window so users can build automations and
        ApexCharts graphs on it.

        The list always spans the whole 24h window: blocks whose prices are
        not published yet appear with ``null`` values ("unknown"), so charts
        show a gap there instead of missing data.
        """
        data = self.coordinator.data
        return {
            "scores_24h": [
                {
                    "start": entry["start"],
                    "price": _round(entry["price"], 5),
                    "effective_price": _round(entry["effective_price"], 5),
                    "pv": _round(entry["pv"], 1),
                    "score": _round(entry["score"], 1),
                    "relative_score": _round(entry["relative_score"], 1),
                    "rank": entry["rank"],
                }
                for entry in data["scores"]
            ],
            "best_blocks": data["best_blocks"],
            "hours_available": data["hours_available"],
            "block_minutes": data["block_minutes"],
        }


def _day_entry(scores: list[dict]) -> list[dict]:
    """Round a day's score list into attribute form (one entry per block)."""
    return [
        {
            "start": s["start"],
            "price": _round(s["price"], 5),
            "effective_price": _round(s["effective_price"], 5),
            "pv": _round(s["pv"], 1),
            "score": _round(s["score"], 1),
            "relative_score": _round(s["relative_score"], 1),
            "rank": s["rank"],
        }
        for s in scores
    ]


def _best_hour(scores: list[dict]) -> str | None:
    """ISO start of the highest-ranked (best) block of a day, or None."""
    if not scores:
        return None
    return max(scores, key=lambda s: s["rank"])["start"]


class SemsRankSensor(SemsSensorBase):
    """Rank of the current block within TODAY: 1 = worst, 24 = best.

    Ranked against the whole calendar day, so the scale is a stable 1..24
    (1..96 with quarter-hour blocks) from midnight to midnight — "rank
    above 19" means the same thing all day, morning included.

    The ``scores`` attribute carries **both** today and tomorrow (up to 48h
    / 192 blocks), each block with its per-day rank and a real timestamp,
    so a chart plotting ``scores`` shows both days and the rank resets to
    1 at midnight. ``best_hour_today`` / ``best_hour_tomorrow`` give the
    single best block of each day; tomorrow is empty until its prices are
    published (~13:00 CET).

    (Before v0.5.0 this data was split over sensor.sems_rank_today and
    sensor.sems_rank_tomorrow. Before v0.4.0 the state ranked within the
    rolling window, whose scale shrank in the morning. The rolling
    per-block ranks are still in scores_24h on sensor.sems_relative_score.)
    """

    _attr_name = "Rank"
    _attr_icon = "mdi:podium"
    _attr_state_class = SensorStateClass.MEASUREMENT
    # scores holds up to ~26 KB (192 blocks in quarter mode): keep this
    # forecast blob out of the recorder (16 KB limit). Live value stays.
    _unrecorded_attributes = frozenset({"scores"})

    def __init__(self, coordinator: SemsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "rank")

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        rank = data.get("current_rank_today")
        if rank is None:
            # Today's prices don't cover the current block (unusual: most
            # sources publish the whole day). Fall back to the rolling
            # window so the sensor still says something sensible.
            rank = data["current"]["rank"]
        return rank

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        today = data.get("today") or []
        tomorrow = data.get("tomorrow") or []
        per_day = data.get("current_rank_today") is not None
        return {
            "current_rank": data.get("current_rank_today"),
            # Both calendar days back to back, each ranked 1..N within
            # itself. Charts read this single attribute for the full view.
            "scores": _day_entry(today) + _day_entry(tomorrow),
            "best_hour_today": _best_hour(today),
            "best_hour_tomorrow": _best_hour(tomorrow),
            # Highest rank reachable today = number of blocks ranked.
            "hours_available": data["today_hours"] if per_day else data["hours_available"],
            "ranked_within": "today" if per_day else "rolling window (fallback)",
            "block_minutes": data["block_minutes"],
        }


class SemsCurrentPriceSensor(SemsSensorBase):
    """The converted ALL-IN price of the current hour (€/kWh).

    This is the price all thresholds and scores operate on, exposed so
    users can verify the raw -> all-in tax conversion against their own
    energy contract.
    """

    _attr_name = "Current price"
    _attr_icon = "mdi:currency-eur"
    _attr_native_unit_of_measurement = "EUR/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator: SemsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "current_price")

    @property
    def native_value(self) -> float | None:
        return round(self.coordinator.data["current"]["price"], 5)

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        return {
            "price_type": data["price_type"],
            "export_price": round(data["current"]["export_price"], 5),
            "effective_price": round(data["current"]["effective_price"], 5),
        }


class SemsDiagnosticsSensor(SemsSensorBase):
    """TEMPORARY verification sensor (only created in debug mode).

    The state is a short plain-language health message; the attributes
    show every intermediate list (raw prices, all-in prices, export
    prices, PV watts) so a non-developer can check the math hour by hour.
    Disable debug mode in the options to remove this sensor.
    """

    _attr_name = "Diagnostics"
    _attr_icon = "mdi:stethoscope"
    _unrecorded_attributes = frozenset({"hourly_overview"})

    def __init__(self, coordinator: SemsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "diagnostics")

    @property
    def native_value(self) -> str:
        data = self.coordinator.data
        # Peak over the whole known forecast rather than the current window,
        # which is all zeroes at night and would read as "no PV data".
        pv_peak = data["pv_peak_watts"]
        ratio = data["pv_peak_ratio"]
        if pv_peak <= 0:
            pv_note = "no PV data (treated as 0 W)"
        elif ratio is None:
            pv_note = f"PV forecast peaks at {pv_peak:.0f} W"
        else:
            # Stating the peak as a share of the configured capacity makes a
            # misconfigured forecast integration visible at a glance: solar
            # coverage is forecast / capacity, so a forecast stuck at a
            # fraction of the array quietly flattens every score.
            pv_note = (
                f"PV forecast peaks at {pv_peak:.0f} W "
                f"({ratio * 100:.0f}% of capacity)"
            )
        # The sanity check guards against a price-type/entity mismatch and
        # an implausibly low solar forecast; the full explanation is in the
        # sanity_check attribute.
        prefix = "OK" if data["sanity_check"] == "OK" else "CHECK SETTINGS"
        return f"{prefix} - {data['hours_available']}h of prices, {pv_note}"

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        # One human-checkable row per hour, so a user can compare every
        # number against the source integration (price app, Energy
        # dashboard) with their own eyes.
        hourly_overview = [
            {
                "hour": entry["start"][:16].replace("T", " "),
                "pv_forecast_w": round(entry["pv"]),
                "raw_price": raw_price,
                "all_in_price": round(entry["price"], 5),
                "export_price": round(entry["export_price"], 5),
                "effective_price": round(entry["effective_price"], 5),
                "score": round(entry["score"], 1),
                "rank": entry["rank"],
            }
            for entry, raw_price in zip(data["scores"], data["raw_prices"])
        ]
        return {
            "price_source": data["price_source"],
            "pv_source": data["pv_source"],
            "price_type": data["price_type"],
            "sanity_check": data["sanity_check"],
            "pv_capacity": data["pv_capacity"],
            "pv_peak_watts": round(data["pv_peak_watts"]),
            "pv_peak_percent_of_capacity": (
                None
                if data["pv_peak_ratio"] is None
                else round(data["pv_peak_ratio"] * 100, 1)
            ),
            "hours_available": data["hours_available"],
            "block_minutes": data["block_minutes"],
            "balance": data["balance"],
            "hourly_overview": hourly_overview,
            "last_computed": data["last_computed"],
        }


class SemsSeriesSensorBase(SemsSensorBase):
    """Base for the debug series sensors (debug mode only).

    Each of these sensors shows one data series as it flows through SEMS:
    the state is the value for the CURRENT block, and the ``series``
    attribute holds the value per block for the whole window — ideal for
    charting a single ingredient of the score with ApexCharts.
    """

    _attr_state_class = SensorStateClass.MEASUREMENT
    _unrecorded_attributes = frozenset({"series"})

    def _series(self, field: str, digits: int) -> list[dict]:
        return [
            {"start": entry["start"], "value": _round(entry[field], digits)}
            for entry in self.coordinator.data["scores"]
        ]


class SemsSourcePriceSensor(SemsSeriesSensorBase):
    """DEBUG: the price exactly as read from the source entity (per block).

    Compare this against the source integration to verify SEMS reads the
    right numbers before any conversion happens.
    """

    _attr_name = "Source price"
    _attr_icon = "mdi:import"
    _attr_native_unit_of_measurement = "EUR/kWh"
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator: SemsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "source_price")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data["source_prices"][0]

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        return {
            "price_source": data["price_source"],
            "price_type": data["price_type"],
            "series": [
                {"start": entry["start"], "value": value}
                for entry, value in zip(data["scores"], data["source_prices"])
            ],
        }


class SemsEffectivePriceSensor(SemsSeriesSensorBase):
    """DEBUG: what one kWh really costs you, per block (€/kWh).

    The heart of the score: grid price and export price blended by how much
    of your consumption your own solar power covers.
    """

    _attr_name = "Effective price"
    _attr_icon = "mdi:cash-multiple"
    _attr_native_unit_of_measurement = "EUR/kWh"
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator: SemsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "effective_price")

    @property
    def native_value(self) -> float | None:
        return _round(self.coordinator.data["current"]["effective_price"], 5)

    @property
    def extra_state_attributes(self) -> dict:
        return {"series": self._series("effective_price", 5)}


class SemsPvForecastSensor(SemsSeriesSensorBase):
    """DEBUG: the solar forecast SEMS is working with, per block (W)."""

    _attr_name = "PV forecast"
    _attr_icon = "mdi:solar-power"
    _attr_native_unit_of_measurement = "W"
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: SemsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "pv_forecast")

    @property
    def native_value(self) -> float | None:
        return _round(self.coordinator.data["current"]["pv"], 1)

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        return {"pv_source": data["pv_source"], "series": self._series("pv", 1)}
