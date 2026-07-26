"""Tests for the Traefik sensors and binary sensors."""

from __future__ import annotations

from unittest.mock import AsyncMock

from traefik import Metrics, SectionCounts, Service

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_instance_sensors(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The headline instance sensors read from the overview."""
    assert hass.states.get("sensor.192_0_2_10_http_routers").state == "8"
    assert hass.states.get("sensor.192_0_2_10_http_router_errors").state == "1"
    assert hass.states.get("sensor.192_0_2_10_http_services").state == "7"
    assert hass.states.get("sensor.192_0_2_10_http_service_errors").state == "0"
    assert hass.states.get("sensor.192_0_2_10_certificates").state == "2"
    assert hass.states.get("sensor.192_0_2_10_version").state == "3.7.6"
    assert (
        hass.states.get("sensor.192_0_2_10_started").state
        == "2026-01-01T00:00:00+00:00"
    )


async def test_metrics_sensors(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The metrics-backed sensors read from /metrics."""
    assert hass.states.get("sensor.192_0_2_10_open_connections").state == "8"
    assert hass.states.get("sensor.192_0_2_10_configuration_reloads").state == "4"
    assert (
        hass.states.get("sensor.192_0_2_10_last_configuration_reload").state
        == "2026-01-02T00:00:00+00:00"
    )
    assert (
        hass.states.get("sensor.192_0_2_10_certificate_expiry").state
        == "2026-04-01T00:00:00+00:00"
    )


async def test_certificate_expiry_without_metrics(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Without metrics the expiry sensor is unknown, not zero."""
    mock_client.get_metrics.return_value = Metrics()
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert (
        hass.states.get("sensor.192_0_2_10_certificate_expiry").state
        == STATE_UNKNOWN
    )
    assert (
        hass.states.get("sensor.192_0_2_10_open_connections").state == STATE_UNKNOWN
    )


async def test_disabled_by_default(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The noisier counters exist but stay switched off."""
    registry = er.async_get(hass)
    for entity_id in (
        "sensor.192_0_2_10_http_middlewares",
        "sensor.192_0_2_10_tcp_routers",
        "sensor.192_0_2_10_udp_routers",
        "sensor.192_0_2_10_entry_points",
    ):
        entry = registry.async_get(entity_id)
        assert entry is not None
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert hass.states.get(entity_id) is None


async def test_router_sensor(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A tracked router gets a status sensor with its configuration attached."""
    state = hass.states.get("sensor.example_file_status")
    assert state.state == "enabled"
    assert state.attributes["rule"] == "Host(`example.test`)"
    assert state.attributes["service"] == "example"
    assert state.attributes["priority"] == 42
    assert state.attributes["entry_points"] == "websecure"
    assert state.attributes["middlewares"] == "compress"
    assert state.attributes["tls"] is True

    assert hass.states.get("binary_sensor.example_file_problem").state == STATE_OFF


async def test_router_disappearing(
    hass: HomeAssistant, mock_client: AsyncMock, setup_integration: MockConfigEntry
) -> None:
    """A router removed from the configuration goes unavailable, not stale."""
    mock_client.list_routers.return_value = []
    await setup_integration.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.example_file_status").state == "unavailable"


async def test_configuration_problem(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """The problem sensor follows the overview's error counts."""
    assert (
        hass.states.get("binary_sensor.192_0_2_10_configuration_problem").state
        == STATE_ON
    )

    overview = mock_client.get_overview.return_value
    mock_client.get_overview.return_value = type(overview)(
        **{
            **{f.name: getattr(overview, f.name) for f in overview.__dataclass_fields__.values()},
            "http_routers": SectionCounts(total=8, warnings=0, errors=0),
        }
    )
    await setup_integration.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert (
        hass.states.get("binary_sensor.192_0_2_10_configuration_problem").state
        == STATE_OFF
    )


async def test_backend_unhealthy(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A probed server going down turns the sensor on."""
    assert (
        hass.states.get("binary_sensor.192_0_2_10_backend_unhealthy").state
        == STATE_OFF
    )

    mock_client.list_services.return_value = [
        Service(
            name="example@file",
            status="enabled",
            provider="file",
            type="loadbalancer",
            server_status={"http://192.0.2.20:8000": "DOWN"},
            used_by=(),
        )
    ]
    await setup_integration.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert (
        hass.states.get("binary_sensor.192_0_2_10_backend_unhealthy").state
        == STATE_ON
    )


async def test_backend_unhealthy_unknown_without_health_checks(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """With nothing probed the state is unknown — "off" would be a lie."""
    mock_client.list_services.return_value = [
        Service(
            name="api@internal",
            status="enabled",
            provider="internal",
            type=None,
            server_status={},
            used_by=(),
        )
    ]
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert (
        hass.states.get("binary_sensor.192_0_2_10_backend_unhealthy").state
        == STATE_UNKNOWN
    )
