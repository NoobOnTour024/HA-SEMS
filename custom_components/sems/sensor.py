"""The SEMS sensors.

Five sensors are created (the last one only when debug mode is on):

* ``sensor.sems_relative_score`` — 0–100%, current hour vs the 24h window.
                                   Carries the full 24h breakdown in the
                                   ``scores_24h`` attribute — this is the
                                   main sensor for automations and charts.
* ``sensor.sems_rank``           — 1..24, rank of the current hour
                                   (1 = worst, 24 = best).
* ``sensor.sems_current_price``  — the converted all-in price of the current
                                   hour, so users can verify the tax math.
* ``sensor.sems_score``          — the raw internal score of the current
                                   hour. Advanced: disabled by default,
                                   because it is easily confused with the
                                   relative score (see the class docstring).
* ``sensor.sems_diagnostics``    — TEMPORARY verification aid (debug mode):
                                   a plain-language health message with all
                                   intermediate numbers as attributes.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEBUG_MODE, DEFAULT_DEBUG_MODE, DOMAIN
from .coordinator import SemsCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the SEMS sensors for this config entry."""
    coordinator: SemsCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        SemsScoreSensor(coordinator, entry),
        SemsRelativeScoreSensor(coordinator, entry),
        SemsRankSensor(coordinator, entry),
        SemsCurrentPriceSensor(coordinator, entry),
    ]
    # The diagnostics sensor is a temporary verification aid; it only
    # exists while debug mode is enabled in the options.
    debug = entry.options.get(CONF_DEBUG_MODE, entry.data.get(CONF_DEBUG_MODE, DEFAULT_DEBUG_MODE))
    if debug:
        entities.append(SemsDiagnosticsSensor(coordinator, entry))

    async_add_entities(entities)


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

    def __init__(self, coordinator: SemsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "relative_score")

    @property
    def native_value(self) -> float | None:
        return round(self.coordinator.data["current"]["relative_score"], 1)

    @property
    def extra_state_attributes(self) -> dict:
        """Expose the full window so users can build automations and
        ApexCharts graphs on it."""
        data = self.coordinator.data
        return {
            "scores_24h": [
                {
                    "start": entry["start"],
                    "price": round(entry["price"], 5),
                    "effective_price": round(entry["effective_price"], 5),
                    "pv": round(entry["pv"], 1),
                    "score": round(entry["score"], 1),
                    "relative_score": round(entry["relative_score"], 1),
                    "rank": entry["rank"],
                }
                for entry in data["scores"]
            ],
            "hours_available": data["hours_available"],
        }


class SemsRankSensor(SemsSensorBase):
    """Rank of the current hour within the window: 1 = worst, 24 = best."""

    _attr_name = "Rank"
    _attr_icon = "mdi:podium"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: SemsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "rank")

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data["current"]["rank"]

    @property
    def extra_state_attributes(self) -> dict:
        # hours_available matters for rank automations: with only 12 hours
        # of data the best possible rank is 12, not 24.
        return {"hours_available": self.coordinator.data["hours_available"]}


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

    def __init__(self, coordinator: SemsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "diagnostics")

    @property
    def native_value(self) -> str:
        data = self.coordinator.data
        pv_peak = max(data["pv_watts"]) if data["pv_watts"] else 0.0
        if pv_peak > 0:
            pv_note = f"PV forecast found (peak {pv_peak:.0f} W)"
        else:
            pv_note = "no PV data (treated as 0 W)"
        return f"OK - {data['hours_available']}h of prices, {pv_note}"

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
            "pv_capacity": data["pv_capacity"],
            "hours_available": data["hours_available"],
            "balance": data["balance"],
            "hourly_overview": hourly_overview,
            "last_computed": data["last_computed"],
        }
