"""Pytest configuration for the SEMS test suite.

The calculator tests run on plain Python everywhere. The config-flow tests
need the pytest-homeassistant-custom-component plugin (a full Home
Assistant test harness); when that is not installed — e.g. on a quick
local run — those tests are simply skipped instead of erroring out.
"""

import importlib.util

collect_ignore: list[str] = []

if importlib.util.find_spec("pytest_homeassistant_custom_component") is None:
    # No Home Assistant test harness available: only run the pure tests.
    collect_ignore.append("test_config_flow.py")
else:
    pytest_plugins = "pytest_homeassistant_custom_component"

    import pytest

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(enable_custom_integrations):
        """Allow Home Assistant to load integrations from custom_components/."""
        yield
