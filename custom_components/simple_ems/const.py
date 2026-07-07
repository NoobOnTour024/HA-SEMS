"""Constants for the SEMS (Simple Energy Management System) integration.

This file holds every fixed value used by the integration: the domain name,
the keys under which configuration is stored, and the default values for
all optional settings. Keeping them in one place means the config flow,
coordinator, and entities all agree on the same names and defaults.
"""

# The integration domain. This is the unique technical name of the
# integration inside Home Assistant (used in entity ids, config entries,
# and the folder name under custom_components/).
DOMAIN = "simple_ems"

# ---------------------------------------------------------------------------
# Configuration keys (used by the config flow and options flow)
# ---------------------------------------------------------------------------

# Required: the entity that provides hourly electricity prices.
CONF_PRICE_ENTITY = "price_entity"

# Optional: the entity that provides the hourly PV production forecast (Watts).
# When not configured, SEMS treats all PV values as 0.
CONF_PV_FORECAST_ENTITY = "pv_forecast_entity"

# Whether the source price is already "all-in" (taxes included) or "raw"
# (bare market/spot price that still needs taxes added).
CONF_PRICE_TYPE = "price_type"
PRICE_TYPE_ALL_IN = "all_in"
PRICE_TYPE_RAW = "raw"

# The three tax/markup fields. When price_type == "raw" they convert the
# source price into the all-in price. When price_type == "all_in" they are
# used in reverse, to estimate the raw market price hidden inside the all-in
# price (needed to know what exporting a kWh earns).
CONF_SUPPLIER_MARKUP = "supplier_markup"  # €/kWh, excl. VAT
CONF_ENERGY_TAX = "energy_tax"  # €/kWh, excl. VAT
CONF_VAT_PERCENT = "vat_percent"  # e.g. 21 for 21% VAT

# Below this ALL-IN price, power counts as "free" (bonus score above 100).
CONF_PRICE_FREE_THRESHOLD = "price_free_threshold"

# The fee the grid/energy company charges per exported kWh ("terugleverkosten").
# Exporting earns: raw market price - export fee (taxes are never paid back).
CONF_EXPORT_FEE = "export_fee"

# Total installed PV capacity in Watt-peak (e.g. 5000 for a 5 kWp system).
# Used to estimate how much of the consumption is covered by own solar power.
# 0 = unknown: assume the sunniest forecast hour of the day covers it.
CONF_PV_CAPACITY = "pv_capacity"

# The time resolution SEMS plans in. Hour blocks (default) suit devices
# that cannot switch quickly (e.g. heat pumps); quarter-hour blocks follow
# the 15-minute market prices some suppliers already use.
CONF_RESOLUTION = "resolution"
RESOLUTION_HOUR = "hour"
RESOLUTION_QUARTER = "quarter_hour"

# Temporary verification aid: when enabled, SEMS creates a diagnostics
# sensor plus separate source-price / effective-price / PV-forecast sensors
# that show exactly what data SEMS found and computed.
CONF_DEBUG_MODE = "debug_mode"

# ---------------------------------------------------------------------------
# Default values (chosen so SEMS works out of the box after selecting the
# two source entities; only price_type == "raw" users need to check the taxes)
# ---------------------------------------------------------------------------

DEFAULT_PRICE_TYPE = PRICE_TYPE_ALL_IN
DEFAULT_SUPPLIER_MARKUP = 0.020  # €/kWh excl. VAT, typical Dutch supplier purchasing fee
DEFAULT_ENERGY_TAX = 0.0916  # €/kWh excl. VAT, Dutch "energiebelasting" 2026
DEFAULT_VAT_PERCENT = 21  # Dutch VAT percentage
DEFAULT_PRICE_FREE_THRESHOLD = 0.00  # €/kWh (all-in)
DEFAULT_EXPORT_FEE = 0.020  # €/kWh, typical Dutch feed-in fee ("terugleverkosten")
DEFAULT_PV_CAPACITY = 0  # W-peak; 0 = unknown (normalise on the day's sunniest hour)
DEFAULT_BALANCE = 50  # slider midpoint: price and PV matter equally
DEFAULT_RESOLUTION = RESOLUTION_HOUR
DEFAULT_DEBUG_MODE = True  # temporarily ON so non-developers can verify the setup

# ---------------------------------------------------------------------------
# Behaviour constants
# ---------------------------------------------------------------------------

# The scoring window: the current block plus the rest of the next 24 hours.
WINDOW_HOURS = 24

# Below this number of available price hours, the data is considered too thin
# to produce meaningful scores: entities become unavailable and a warning is
# logged (this typically only happens when a price source is broken).
MIN_HOURS_REQUIRED = 6

# The appliance-block durations (in hours) for which SEMS creates
# "best block" binary sensors: e.g. a dishwasher that needs 2 hours.
BLOCK_DURATIONS_HOURS = (2, 3, 4)
