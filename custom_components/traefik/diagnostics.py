"""Diagnostics for the Traefik integration.

Users paste this output into issue reports. A Traefik configuration is a map of
someone's private network — hostnames, internal IPs and ports, service names —
so it is redacted here rather than trusted to be uninteresting.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_METRICS_URL
from .coordinator import TraefikConfigEntry

# async_redact_data matches keys exactly, so every variant has to be listed.
TO_REDACT = {
    CONF_METRICS_URL,
    CONF_PASSWORD,
    CONF_URL,
    CONF_USERNAME,
    "address",
    "common_name",
    "metrics_url",
    "password",
    "rule",
    "url",
    "username",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TraefikConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data

    overview: dict[str, Any] = {}
    if data is not None:
        overview = {
            section: {
                "total": counts.total,
                "warnings": counts.warnings,
                "errors": counts.errors,
            }
            for section, counts in (
                ("http_routers", data.overview.http_routers),
                ("http_services", data.overview.http_services),
                ("http_middlewares", data.overview.http_middlewares),
                ("tcp_routers", data.overview.tcp_routers),
                ("tcp_services", data.overview.tcp_services),
                ("udp_routers", data.overview.udp_routers),
            )
        }

    services: dict[str, Any] = {}
    if data is not None:
        # Service names are chosen by the user and routinely say what the
        # backend is, so they are reduced to an index. What matters for a bug
        # report is the shape: how many are probed, and how many are down.
        probed = [s for s in data.services.values() if s.has_health_check]
        services = {
            "total": len(data.services),
            "with_health_check": len(probed),
            "with_a_server_down": sum(1 for s in probed if s.all_servers_up is False),
            "not_enabled": sum(1 for s in data.services.values() if not s.enabled),
        }

    routers: dict[str, Any] = {}
    if data is not None:
        routers = {
            "total": len(data.routers),
            "not_enabled": sum(1 for r in data.routers.values() if not r.enabled),
            "with_tls": sum(1 for r in data.routers.values() if r.tls),
            "providers": sorted(
                {r.provider for r in data.routers.values() if r.provider}
            ),
        }

    return {
        "entry": {
            # Only the count. The option itself is a list of router names, and
            # those are hostnames in all but name.
            "tracked_router_count": len(entry.options.get("routers", [])),
            "data": async_redact_data(dict(entry.data), TO_REDACT),
        },
        "version": data.server.version if data else None,
        "codename": data.server.codename if data else None,
        "providers": list(data.overview.providers) if data else None,
        "metrics_provider": data.overview.metrics_provider if data else None,
        "access_log": data.overview.access_log if data else None,
        "certificates": data.overview.certificates if data else None,
        "entrypoint_count": len(data.entrypoints) if data else None,
        "metrics_available": bool(data and data.metrics.open_connections is not None),
        "last_update_success": coordinator.last_update_success,
        "overview": overview,
        "routers": routers,
        "services": services,
    }
