"""The SEMS balance slider.

``number.sems_balance`` is a 0–100 slider that decides what "a good hour"
means:

* 100 — only the (effective) price matters,
* 0   — only PV self-consumption matters,
* 50  — both matter equally (the default).

The value survives Home Assistant restarts (RestoreNumber) and every
change immediately triggers a recomputation of all scores.
"""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_BALANCE, DOMAIN
from .coordinator import SemsCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the balance slider for this config entry."""
    coordinator: SemsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SemsBalanceNumber(coordinator, entry)])


class SemsBalanceNumber(RestoreNumber):
    """The price-vs-PV balance slider (0–100, step 1, default 50)."""

    _attr_has_entity_name = True
    _attr_name = "Balance"
    _attr_icon = "mdi:scale-balance"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: SemsCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_native_value = float(DEFAULT_BALANCE)
        self._attr_unique_id = f"{entry.entry_id}_balance"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="SEMS",
            manufacturer="SEMS",
            model="Simple Energy Management System",
        )

    async def async_added_to_hass(self) -> None:
        """Restore the slider position from before the last restart."""
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = last.native_value
            self._coordinator.balance = int(last.native_value)
            # Recompute with the restored balance (the first computation ran
            # with the default before this entity was restored).
            await self._coordinator.async_request_refresh()

    async def async_set_native_value(self, value: float) -> None:
        """Handle the user moving the slider: store and recompute."""
        self._attr_native_value = value
        self._coordinator.balance = int(value)
        self.async_write_ha_state()
        await self._coordinator.async_request_refresh()
