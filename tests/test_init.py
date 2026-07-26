"""Tests for setting up and tearing down the Traefik integration."""

from __future__ import annotations

from unittest.mock import AsyncMock

from traefik import TraefikAuthenticationError, TraefikConnectionError

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.traefik.const import CONF_ROUTERS, DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import ROUTER


async def test_setup_and_unload(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The entry loads and unloads cleanly."""
    assert setup_integration.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    await hass.async_block_till_done()
    assert setup_integration.state is ConfigEntryState.NOT_LOADED


async def test_devices(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """The instance device exists, and the router hangs off it."""
    registry = dr.async_get(hass)
    instance = registry.async_get_device(
        identifiers={(DOMAIN, setup_integration.entry_id)}
    )
    assert instance is not None
    assert instance.sw_version == "3.7.6"

    router = registry.async_get_device(
        identifiers={(DOMAIN, f"{setup_integration.entry_id}_{ROUTER}")}
    )
    assert router is not None
    assert router.via_device_id == instance.id


async def test_setup_retries_when_unreachable(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """An unreachable instance is a retry, not a failure."""
    mock_client.get_version.side_effect = TraefikConnectionError("down")
    config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_triggers_reauth(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Being refused starts a reauth flow instead of retrying forever."""
    mock_client.get_version.side_effect = TraefikAuthenticationError("denied")
    config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR

    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_optional_endpoints_are_not_fatal(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """Losing metrics or entrypoints still leaves a working entry."""
    mock_client.get_metrics.side_effect = TraefikConnectionError("firewalled")
    mock_client.list_entrypoints.side_effect = TraefikConnectionError("firewalled")
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED

    data = config_entry.runtime_data.data
    assert data.metrics.open_connections is None
    assert data.entrypoints == ()


async def test_entrypoints_fetched_once(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """Entry points only change on restart, so they are cached."""
    await setup_integration.runtime_data.async_refresh()
    assert mock_client.list_entrypoints.await_count == 1
    assert mock_client.get_overview.await_count == 2


async def test_options_change_reloads(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Changing the tracked routers rebuilds the entities."""
    hass.config_entries.async_update_entry(
        setup_integration, options={CONF_ROUTERS: []}
    )
    await hass.async_block_till_done()

    assert setup_integration.state is ConfigEntryState.LOADED
    # The registry entry survives an untrack, so the state is the restored
    # placeholder rather than nothing at all.
    state = hass.states.get("sensor.example_file_status")
    assert state.state == "unavailable"
    assert state.attributes.get("restored") is True
