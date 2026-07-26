"""Tests for Traefik diagnostics.

A diagnostics file gets pasted into public bug reports, and a Traefik
configuration is a map of someone's private network — so anything identifying
that leaks here leaks there.
"""

from __future__ import annotations

import json

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from .conftest import METRICS_URL, ROUTER, URL


async def test_diagnostics_redacts_identifying_data(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    setup_integration: MockConfigEntry,
) -> None:
    """No address, rule, hostname, router or certificate name gets out."""
    result = await get_diagnostics_for_config_entry(
        hass, hass_client, setup_integration
    )
    blob = json.dumps(result)

    for secret in (
        URL,
        METRICS_URL,
        ROUTER,
        "192.0.2.10",
        "192.0.2.20",
        "example.test",
        "Host(`example.test`)",
    ):
        assert secret not in blob, f"{secret!r} leaked into diagnostics"


async def test_diagnostics_still_useful(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    setup_integration: MockConfigEntry,
) -> None:
    """What survives redaction is enough to debug with."""
    result = await get_diagnostics_for_config_entry(
        hass, hass_client, setup_integration
    )

    assert result["version"] == "3.7.6"
    assert result["metrics_provider"] == "Prometheus"
    assert result["metrics_available"] is True
    assert result["entrypoint_count"] == 2
    assert result["last_update_success"] is True
    assert result["entry"]["tracked_router_count"] == 1
    assert result["overview"]["http_routers"] == {
        "total": 8,
        "warnings": 0,
        "errors": 1,
    }
    assert result["routers"] == {
        "total": 1,
        "not_enabled": 0,
        "with_tls": 1,
        "providers": ["file"],
    }
    assert result["services"] == {
        "total": 2,
        "with_health_check": 1,
        "with_a_server_down": 0,
        "not_enabled": 0,
    }
