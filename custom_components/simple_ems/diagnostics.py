"""Diagnostics for SEMS.

Adds a "Download diagnostics" button to the SEMS integration page
(Settings -> Devices & services -> SEMS -> the three dots). The download
contains everything needed to reproduce what SEMS did, without any
credentials:

* your settings (which entities, price type, taxes, resolution, ...),
* everything SEMS computed (the rolling window, both calendar days, the
  best blocks, the sanity check),
* the RAW state and attributes of your price and PV source entities.

That last part is the important one: with it, the exact same numbers can
be replayed through the calculator on any machine, so a problem can be
verified instead of guessed at.
"""

from __future__ import annotations

import json
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_PRICE_ENTITY, CONF_PV_FORECAST_ENTITY, DOMAIN
from .coordinator import SemsCoordinator


def _jsonable(value: Any) -> Any:
    """Make a value safe to write to the diagnostics file.

    Source integrations often put datetime objects in their attributes,
    which json cannot serialise; ``default=str`` turns those into ISO
    strings instead of failing the whole download.
    """
    return json.loads(json.dumps(value, default=str))


def _dump_source(hass: HomeAssistant, entity_id: str | None) -> dict | None:
    """Dump a source entity exactly as SEMS sees it."""
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None:
        return {"entity_id": entity_id, "state": "ENTITY NOT FOUND"}
    return {
        "entity_id": entity_id,
        "state": state.state,
        "attributes": _jsonable(dict(state.attributes)),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return everything SEMS knows, for troubleshooting."""
    coordinator: SemsCoordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "config": {
            "data": _jsonable(dict(entry.data)),
            "options": _jsonable(dict(entry.options)),
        },
        "balance_slider": coordinator.balance,
        "computed": _jsonable(coordinator.data),
        "sources": {
            "price": _dump_source(hass, entry.data.get(CONF_PRICE_ENTITY)),
            "pv_forecast": _dump_source(hass, entry.data.get(CONF_PV_FORECAST_ENTITY)),
        },
    }
