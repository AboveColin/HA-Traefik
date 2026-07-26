"""Shared fixtures for the Traefik tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from traefik import (
    Certificate,
    EntryPoint,
    Metrics,
    Overview,
    Router,
    SectionCounts,
    ServerInfo,
    Service,
    TrafficStats,
)

from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant

from custom_components.traefik.const import (
    CONF_METRICS_URL,
    CONF_ROUTERS,
    CONF_TRACK_ALL,
    CONF_VERIFY_SSL,
    DOMAIN,
)

from pytest_homeassistant_custom_component.common import MockConfigEntry

URL = "http://192.0.2.10:8080"
METRICS_URL = "http://192.0.2.10:8082"
ROUTER = "example@file"
HOSTNAME = "example.test"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load the integration from custom_components."""


@pytest.fixture
def server_info() -> ServerInfo:
    """Return a version response."""
    return ServerInfo(
        version="3.7.6",
        codename="langres",
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.fixture
def overview() -> Overview:
    """Return an overview with one router error."""
    return Overview(
        http_routers=SectionCounts(total=8, warnings=0, errors=1),
        http_services=SectionCounts(total=7, warnings=0, errors=0),
        http_middlewares=SectionCounts(total=3, warnings=0, errors=0),
        tcp_routers=SectionCounts(total=1, warnings=0, errors=0),
        tcp_services=SectionCounts(total=1, warnings=0, errors=0),
        tcp_middlewares=SectionCounts(total=0, warnings=0, errors=0),
        udp_routers=SectionCounts(total=0, warnings=0, errors=0),
        udp_services=SectionCounts(total=0, warnings=0, errors=0),
        certificates=2,
        providers=("File",),
        metrics_provider="Prometheus",
        access_log=True,
        tracing_provider=None,
    )


@pytest.fixture
def router() -> Router:
    """Return an enabled router."""
    return Router(
        name=ROUTER,
        rule="Host(`example.test`)",
        service="example",
        status="enabled",
        provider="file",
        priority=42,
        entry_points=("websecure",),
        middlewares=("compress",),
        tls=True,
    )


@pytest.fixture
def services() -> list[Service]:
    """Return one probed service and one that is not probed."""
    return [
        Service(
            name="example@file",
            status="enabled",
            provider="file",
            type="loadbalancer",
            server_status={"http://192.0.2.20:8000": "UP"},
            used_by=(ROUTER,),
            has_health_check=True,
        ),
        Service(
            name="api@internal",
            status="enabled",
            provider="internal",
            type=None,
            server_status={},
            used_by=(),
        ),
    ]


@pytest.fixture
def entrypoints() -> list[EntryPoint]:
    """Return the entry points."""
    return [
        EntryPoint(name="web", address=":80", http2=True, udp=False),
        EntryPoint(name="websecure", address=":443", http2=True, udp=False),
    ]


@pytest.fixture
def metrics() -> Metrics:
    """Return parsed metrics."""
    return Metrics(
        open_connections=8,
        config_reloads=4,
        last_reload=datetime(2026, 1, 2, tzinfo=UTC),
        certificates=(
            Certificate(
                common_name="example.test",
                not_after=datetime(2026, 4, 1, tzinfo=UTC),
                sans=("example.test", "www.example.test"),
            ),
        ),
        services={
            "example@file": TrafficStats(
                requests=200,
                client_errors=8,
                server_errors=2,
                duration_total=50.0,
                duration_count=200,
            )
        },
        entrypoints={
            "websecure": TrafficStats(
                requests=200,
                client_errors=8,
                server_errors=2,
                duration_total=50.0,
                duration_count=200,
            )
        },
        connections_by_entrypoint={"websecure": 8},
    )


@pytest.fixture
def mock_client(
    server_info: ServerInfo,
    overview: Overview,
    router: Router,
    services: list[Service],
    entrypoints: list[EntryPoint],
    metrics: Metrics,
) -> Generator[AsyncMock]:
    """Patch TraefikClient everywhere the integration constructs one."""
    client = AsyncMock()
    client.get_version.return_value = server_info
    client.get_overview.return_value = overview
    client.list_routers.return_value = [router]
    client.list_services.return_value = services
    client.list_entrypoints.return_value = entrypoints
    client.get_metrics.return_value = metrics

    with (
        patch(
            "custom_components.traefik.config_flow.TraefikClient",
            return_value=client,
        ),
        patch("custom_components.traefik.TraefikClient", return_value=client),
    ):
        yield client


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a configured entry tracking every router."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="192.0.2.10:8080",
        unique_id="192.0.2.10:8080",
        data={
            CONF_URL: URL,
            CONF_METRICS_URL: METRICS_URL,
            CONF_VERIFY_SSL: True,
        },
        options={CONF_TRACK_ALL: True, CONF_ROUTERS: []},
    )


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant, mock_client: AsyncMock, config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Add and set up the config entry."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
