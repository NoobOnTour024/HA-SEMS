"""Tests for the SEMS config flow, run against a real Home Assistant core.

These tests drive the setup wizard exactly like the frontend does:
initialize the flow, submit the entity screen, submit the settings screen,
and check that a config entry is created. This is what catches "unknown
error" problems that plain unit tests cannot see.
"""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sems.const import (
    CONF_DEBUG_MODE,
    CONF_ENERGY_TAX,
    CONF_PRICE_ENTITY,
    CONF_PRICE_TYPE,
    CONF_PV_FORECAST_ENTITY,
    CONF_VAT_PERCENT,
    DEFAULT_ENERGY_TAX,
    DEFAULT_PRICE_TYPE,
    DOMAIN,
)


async def test_full_flow_with_defaults(hass: HomeAssistant) -> None:
    """The happy path: pick two entities, accept all defaults."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    # Screen 1: source entities.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_PRICE_ENTITY: "sensor.nordpool_prices",
            CONF_PV_FORECAST_ENTITY: "sensor.solar_forecast",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "settings"

    # Screen 2: submit with all defaults (an empty form submit — voluptuous
    # fills in every default, exactly like the UI does).
    with patch("custom_components.sems.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "SEMS"
    data = result["data"]
    assert data[CONF_PRICE_ENTITY] == "sensor.nordpool_prices"
    assert data[CONF_PV_FORECAST_ENTITY] == "sensor.solar_forecast"
    assert data[CONF_PRICE_TYPE] == DEFAULT_PRICE_TYPE
    assert data[CONF_ENERGY_TAX] == DEFAULT_ENERGY_TAX


async def test_flow_without_pv_entity(hass: HomeAssistant) -> None:
    """The PV forecast entity is optional and may be left empty."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PRICE_ENTITY: "sensor.nordpool_prices"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "settings"

    with patch("custom_components.sems.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_PV_FORECAST_ENTITY not in result["data"]


async def test_options_flow(hass: HomeAssistant) -> None:
    """Settings can be changed later via the Configure button."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="SEMS",
        data={
            CONF_PRICE_ENTITY: "sensor.nordpool_prices",
            CONF_PRICE_TYPE: DEFAULT_PRICE_TYPE,
        },
    )
    entry.add_to_hass(hass)

    with patch("custom_components.sems.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_VAT_PERCENT: 9, CONF_DEBUG_MODE: False}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_VAT_PERCENT] == 9
    assert result["data"][CONF_DEBUG_MODE] is False
