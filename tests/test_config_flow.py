"""Tests for the Traefik config and options flow."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from traefik import (
    TraefikAuthenticationError,
    TraefikConnectionError,
    TraefikResponseError,
)

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.traefik.config_flow import _normalise_url
from custom_components.traefik.const import (
    CONF_METRICS_URL,
    CONF_ROUTERS,
    CONF_VERIFY_SSL,
    DOMAIN,
)

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import METRICS_URL, ROUTER, URL


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )


async def test_user_flow(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """A working address creates an entry."""
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: URL, CONF_METRICS_URL: METRICS_URL, CONF_VERIFY_SSL: True},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "192.0.2.10:8080"
    assert result["result"].unique_id == "192.0.2.10:8080"
    assert result["data"][CONF_URL] == URL
    assert result["options"] == {CONF_ROUTERS: []}


async def test_user_flow_with_credentials(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """Basic-auth credentials are stored."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_URL: URL,
            CONF_USERNAME: "colin",
            CONF_PASSWORD: "hunter2",
            CONF_VERIFY_SSL: False,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_USERNAME] == "colin"
    assert result["data"][CONF_PASSWORD] == "hunter2"
    assert result["data"][CONF_VERIFY_SSL] is False


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (TraefikAuthenticationError("denied"), "invalid_auth"),
        (TraefikConnectionError("down"), "cannot_connect"),
        (TraefikResponseError("nonsense"), "invalid_response"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant, mock_client: AsyncMock, error: Exception, reason: str
) -> None:
    """Every failure mode shows its own message, then recovers."""
    mock_client.get_version.side_effect = error

    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": reason}

    mock_client.get_version.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_already_configured(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """The same host and port cannot be added twice."""
    config_entry.add_to_hass(hass)

    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("192.0.2.10:8080", "http://192.0.2.10:8080"),
        ("http://192.0.2.10:8080/", "http://192.0.2.10:8080"),
        ("http://192.0.2.10:8080/dashboard/", "http://192.0.2.10:8080"),
        ("http://192.0.2.10:8080/api", "http://192.0.2.10:8080"),
        ("http://192.0.2.10:8080/api/overview", "http://192.0.2.10:8080"),
        ("https://traefik.example.test", "https://traefik.example.test"),
    ],
)
def test_normalise_url(raw: str, expected: str) -> None:
    """People paste the dashboard address; take it anyway."""
    assert _normalise_url(raw) == expected


async def test_normalises_metrics_url(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """A bare metrics host gets a scheme too."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL, CONF_METRICS_URL: "192.0.2.10:8082/"}
    )
    assert result["data"][CONF_METRICS_URL] == METRICS_URL


async def test_reauth(
    hass: HomeAssistant, mock_client: AsyncMock, setup_integration: MockConfigEntry
) -> None:
    """Reauth updates the credentials in place."""
    result = await setup_integration.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    mock_client.get_version.side_effect = TraefikAuthenticationError("denied")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "colin", CONF_PASSWORD: "wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    mock_client.get_version.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "colin", CONF_PASSWORD: "right"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert setup_integration.data[CONF_PASSWORD] == "right"


async def test_options_flow(
    hass: HomeAssistant, mock_client: AsyncMock, setup_integration: MockConfigEntry
) -> None:
    """The options flow lists routers and saves the selection."""
    result = await hass.config_entries.options.async_init(
        setup_integration.entry_id
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ROUTERS: [ROUTER]}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert setup_integration.options[CONF_ROUTERS] == [ROUTER]


async def test_options_flow_keeps_missing_router(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    """A tracked router that vanished stays offered, not silently dropped."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_ROUTERS: ["gone@file"]}
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    options = result["data_schema"]({})[CONF_ROUTERS]
    assert options == ["gone@file"]


async def test_options_flow_unreachable(
    hass: HomeAssistant, mock_client: AsyncMock, setup_integration: MockConfigEntry
) -> None:
    """The options flow aborts rather than showing an empty picker."""
    mock_client.list_routers.side_effect = TraefikConnectionError("down")
    result = await hass.config_entries.options.async_init(
        setup_integration.entry_id
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"
