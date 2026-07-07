"""Tests for the SEMS config flow, run against a real Home Assistant core.

These tests drive the setup wizard exactly like the frontend does:
initialize the flow, submit each screen, and check that a config entry is
created. This is what catches "unknown error" problems that plain unit
tests cannot see.
"""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.simple_ems.const import (
    CONF_DEBUG_MODE,
    CONF_ENERGY_TAX,
    CONF_PRICE_ENTITY,
    CONF_PRICE_TYPE,
    CONF_PV_FORECAST_ENTITY,
    CONF_SUPPLIER_MARKUP,
    CONF_VAT_PERCENT,
    DEFAULT_ENERGY_TAX,
    DEFAULT_PRICE_TYPE,
    DEFAULT_SUPPLIER_MARKUP,
    DOMAIN,
    PRICE_TYPE_RAW,
)


async def test_full_flow_with_defaults(hass: HomeAssistant) -> None:
    """The happy path: pick two entities, accept all defaults.

    The taxes screen is shown for every price type (with all-in prices the
    values are used in reverse, for the export-price estimate).
    """
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
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "taxes"

    # Screen 3: taxes, again all defaults.
    with patch("custom_components.simple_ems.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "SEMS"
    data = result["data"]
    assert data[CONF_PRICE_ENTITY] == "sensor.nordpool_prices"
    assert data[CONF_PV_FORECAST_ENTITY] == "sensor.solar_forecast"
    assert data[CONF_PRICE_TYPE] == DEFAULT_PRICE_TYPE
    assert data[CONF_ENERGY_TAX] == DEFAULT_ENERGY_TAX
    assert data[CONF_SUPPLIER_MARKUP] == DEFAULT_SUPPLIER_MARKUP


async def test_raw_price_flow(hass: HomeAssistant) -> None:
    """Raw market prices: same three screens, custom VAT on the taxes one."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PRICE_ENTITY: "sensor.nordpool_prices"}
    )
    assert result["step_id"] == "settings"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PRICE_TYPE: PRICE_TYPE_RAW}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "taxes"

    with patch("custom_components.simple_ems.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_VAT_PERCENT: 9}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PRICE_TYPE] == PRICE_TYPE_RAW
    assert result["data"][CONF_VAT_PERCENT] == 9
    assert result["data"][CONF_ENERGY_TAX] == DEFAULT_ENERGY_TAX


async def test_flow_without_pv_entity(hass: HomeAssistant) -> None:
    """The PV forecast entity is optional and may be left empty."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PRICE_ENTITY: "sensor.nordpool_prices"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "taxes"

    with patch("custom_components.simple_ems.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_PV_FORECAST_ENTITY not in result["data"]


async def test_options_flow_prefills_saved_taxes(hass: HomeAssistant) -> None:
    """Options flow: previously saved tax values are the new defaults, so
    submitting the taxes screen unchanged keeps them."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="SEMS",
        data={
            CONF_PRICE_ENTITY: "sensor.nordpool_prices",
            CONF_PRICE_TYPE: DEFAULT_PRICE_TYPE,
            CONF_ENERGY_TAX: 0.05,  # a custom, non-default value
        },
    )
    entry.add_to_hass(hass)

    with patch("custom_components.simple_ems.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_DEBUG_MODE: False}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "taxes"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DEBUG_MODE] is False
    # The custom tax value was the pre-filled default and survived.
    assert result["data"][CONF_ENERGY_TAX] == 0.05


async def test_options_flow_can_change_taxes(hass: HomeAssistant) -> None:
    """Options flow: tax values can be changed on the taxes screen."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="SEMS",
        data={
            CONF_PRICE_ENTITY: "sensor.nordpool_prices",
            CONF_PRICE_TYPE: DEFAULT_PRICE_TYPE,
        },
    )
    entry.add_to_hass(hass)

    with patch("custom_components.simple_ems.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_PRICE_TYPE: PRICE_TYPE_RAW}
        )
        assert result["step_id"] == "taxes"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SUPPLIER_MARKUP: 0.03}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PRICE_TYPE] == PRICE_TYPE_RAW
    assert result["data"][CONF_SUPPLIER_MARKUP] == 0.03
