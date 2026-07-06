"""The SEMS (Simple Energy Management System) integration.

This file wires everything together when Home Assistant loads the
integration: it creates the coordinator (which does all the reading and
calculating) and hands it to the three entity platforms (sensor,
binary_sensor and number).
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SemsCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.NUMBER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SEMS from a config entry (called when HA starts or the
    integration is added via the UI)."""
    coordinator = SemsCoordinator(hass, entry)

    # Start the hourly clock and the source-entity listeners.
    await coordinator.async_setup()

    # Do the first computation right away. If the source entities are not
    # ready yet, Home Assistant automatically retries the setup later.
    await coordinator.async_config_entry_first_refresh()

    # Make the coordinator available to the entity platforms.
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Create the entities.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload the integration when the user changes options, so new settings
    # take effect immediately.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options being changed by reloading the integration."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload SEMS (called when the integration is removed or reloaded)."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: SemsCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.async_unload()
    return unload_ok
