"""Config flow for SEMS: the setup wizard shown in the Home Assistant UI.

The flow has two steps:

1. ``user``     — pick the two source entities. The price entity is
                  required; the PV forecast entity is optional.
2. ``settings`` — everything else, all pre-filled with sensible defaults,
                  so simply clicking "Submit" gives a working setup.

The same settings can be changed later via the integration's
"Configure" button (the options flow at the bottom of this file).
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_DEBUG_MODE,
    CONF_ENERGY_TAX,
    CONF_EXPORT_FEE,
    CONF_PRICE_ENTITY,
    CONF_PRICE_FREE_THRESHOLD,
    CONF_PRICE_TYPE,
    CONF_PV_CAPACITY,
    CONF_PV_FORECAST_ENTITY,
    CONF_SUPPLIER_MARKUP,
    CONF_VAT_PERCENT,
    DEFAULT_DEBUG_MODE,
    DEFAULT_ENERGY_TAX,
    DEFAULT_EXPORT_FEE,
    DEFAULT_PRICE_FREE_THRESHOLD,
    DEFAULT_PRICE_TYPE,
    DEFAULT_PV_CAPACITY,
    DEFAULT_SUPPLIER_MARKUP,
    DEFAULT_VAT_PERCENT,
    DOMAIN,
    PRICE_TYPE_ALL_IN,
    PRICE_TYPE_RAW,
)


def _settings_schema(current: dict[str, Any]) -> vol.Schema:
    """Build the settings form, pre-filled with ``current`` values.

    Used by both the second setup step (pre-filled with defaults) and the
    options flow (pre-filled with the user's saved settings).
    """
    return vol.Schema(
        {
            vol.Required(
                CONF_PRICE_TYPE,
                default=current.get(CONF_PRICE_TYPE, DEFAULT_PRICE_TYPE),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[PRICE_TYPE_ALL_IN, PRICE_TYPE_RAW],
                    mode=SelectSelectorMode.LIST,
                    translation_key="price_type",
                )
            ),
            vol.Required(
                CONF_SUPPLIER_MARKUP,
                default=current.get(CONF_SUPPLIER_MARKUP, DEFAULT_SUPPLIER_MARKUP),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=1, step=0.0001, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="€/kWh",
                )
            ),
            vol.Required(
                CONF_ENERGY_TAX,
                default=current.get(CONF_ENERGY_TAX, DEFAULT_ENERGY_TAX),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=1, step=0.0001, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="€/kWh",
                )
            ),
            vol.Required(
                CONF_VAT_PERCENT,
                default=current.get(CONF_VAT_PERCENT, DEFAULT_VAT_PERCENT),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=100, step=0.1, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="%",
                )
            ),
            vol.Required(
                CONF_EXPORT_FEE,
                default=current.get(CONF_EXPORT_FEE, DEFAULT_EXPORT_FEE),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=1, step=0.0001, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="€/kWh",
                )
            ),
            vol.Required(
                CONF_PV_CAPACITY,
                default=current.get(CONF_PV_CAPACITY, DEFAULT_PV_CAPACITY),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=100000, step=50, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="W",
                )
            ),
            vol.Required(
                CONF_PRICE_FREE_THRESHOLD,
                default=current.get(CONF_PRICE_FREE_THRESHOLD, DEFAULT_PRICE_FREE_THRESHOLD),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=-1, max=1, step=0.0001, mode=NumberSelectorMode.BOX,
                    unit_of_measurement="€/kWh",
                )
            ),
            vol.Required(
                CONF_DEBUG_MODE,
                default=current.get(CONF_DEBUG_MODE, DEFAULT_DEBUG_MODE),
            ): BooleanSelector(),
        }
    )


class SemsConfigFlow(ConfigFlow, domain=DOMAIN):
    """The two-step setup wizard."""

    VERSION = 1

    def __init__(self) -> None:
        self._entities: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Step 1: pick the source entities."""
        if user_input is not None:
            self._entities = user_input
            return await self.async_step_settings()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PRICE_ENTITY): EntitySelector(
                        EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Optional(CONF_PV_FORECAST_ENTITY): EntitySelector(
                        EntitySelectorConfig(domain="sensor")
                    ),
                }
            ),
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Step 2: prices, taxes and thresholds — all with working defaults."""
        if user_input is not None:
            return self.async_create_entry(
                title="SEMS", data={**self._entities, **user_input}
            )

        return self.async_show_form(
            step_id="settings", data_schema=_settings_schema({})
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SemsOptionsFlow:
        """Tell Home Assistant this integration has a Configure button."""
        return SemsOptionsFlow()


class SemsOptionsFlow(OptionsFlow):
    """Change the settings later via the integration's Configure button.

    (To change the source entities themselves, remove and re-add the
    integration — that keeps this flow simple.)
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Pre-fill with saved options, falling back to the initial setup data.
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=_settings_schema(current)
        )
