"""The SEMS free-power binary sensor.

``binary_sensor.sems_free_power`` is ON when the current ALL-IN price is
below the configured free-power threshold. It is deliberately derived
from the price itself, never from the score.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SemsCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the free-power binary sensor for this config entry."""
    coordinator: SemsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SemsFreePowerBinarySensor(coordinator, entry)])


class SemsFreePowerBinarySensor(CoordinatorEntity[SemsCoordinator], BinarySensorEntity):
    """ON when power is currently 'free' (all-in price below the threshold)."""

    _attr_has_entity_name = True
    _attr_name = "Free power"
    _attr_icon = "mdi:gift-outline"

    def __init__(self, coordinator: SemsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_free_power"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="SEMS",
            manufacturer="SEMS",
            model="Simple Energy Management System",
        )

    @property
    def is_on(self) -> bool:
        # Computed by the coordinator as: current all-in price < threshold.
        return bool(self.coordinator.data["free_power"])

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "current_price": round(self.coordinator.data["current"]["price"], 5),
            "threshold": self.coordinator.free_threshold,
        }
