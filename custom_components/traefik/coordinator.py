"""Data coordinator for the Traefik integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging

from traefik import (
    Certificate,
    EntryPoint,
    Metrics,
    Overview,
    Router,
    ServerInfo,
    Service,
    TraefikAuthenticationError,
    TraefikClient,
    TraefikError,
    TrafficStats,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ROUTERS,
    CONF_TRACK_ALL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TRACK_ALL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

type TraefikConfigEntry = ConfigEntry[TraefikCoordinator]


@dataclass
class TraefikData:
    """One snapshot of an instance."""

    server: ServerInfo
    overview: Overview
    routers: dict[str, Router] = field(default_factory=dict)
    services: dict[str, Service] = field(default_factory=dict)
    entrypoints: tuple[EntryPoint, ...] = ()
    metrics: Metrics = field(default_factory=Metrics)

    def service_for(self, router: Router) -> Service | None:
        """Return the service a router forwards to.

        A router names its service without a provider suffix when both live in
        the same provider (``foo``), but the services list is keyed with it
        (``foo@file``), so the bare name has to be qualified before lookup.
        """
        if not router.service:
            return None
        if (service := self.services.get(router.service)) is not None:
            return service
        if router.provider:
            return self.services.get(f"{router.service}@{router.provider}")
        return None

    def traffic_for(self, router: Router) -> TrafficStats | None:
        """Return the traffic counters for a router's service, if metrics exist."""
        if (service := self.service_for(router)) is None:
            return None
        return self.metrics.services.get(service.name)

    def certificate_for(self, router: Router) -> Certificate | None:
        """Return the certificate serving a router's first hostname."""
        hostnames = router.hostnames
        if not hostnames:
            return None
        return self.metrics.certificate_for(hostnames[0])

    @property
    def hostnames(self) -> tuple[str, ...]:
        """Every distinct hostname served, sorted."""
        return tuple(
            sorted({host for router in self.routers.values() for host in router.hostnames})
        )


class TraefikCoordinator(DataUpdateCoordinator[TraefikData]):
    """Fetch instance state on a schedule."""

    config_entry: TraefikConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: TraefikConfigEntry,
        client: TraefikClient,
    ) -> None:
        """Set up the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client
        self._entrypoints: tuple[EntryPoint, ...] = ()

    @property
    def track_all(self) -> bool:
        """Whether every router gets its own device."""
        return bool(self.config_entry.options.get(CONF_TRACK_ALL, DEFAULT_TRACK_ALL))

    @property
    def tracked_routers(self) -> list[str]:
        """Return the router names that should have entities.

        With ``track_all`` on this follows the live configuration, so a host
        added to Traefik shows up on the next poll without a reload.
        """
        if self.track_all:
            return sorted(self.data.routers) if self.data else []
        return list(self.config_entry.options.get(CONF_ROUTERS, []))

    async def _async_update_data(self) -> TraefikData:
        """Refresh everything."""
        try:
            server, overview, routers, services = await asyncio.gather(
                self.client.get_version(),
                self.client.get_overview(),
                self.client.list_routers(),
                self.client.list_services(),
            )
        except TraefikAuthenticationError as err:
            # Re-auth rather than a generic failure: either the allowlist or
            # the credentials changed, and only the user can fix that.
            raise ConfigEntryAuthFailed(str(err)) from err
        except TraefikError as err:
            raise UpdateFailed(str(err)) from err

        # Entrypoints only change when Traefik is restarted with new flags, so
        # fetching them every minute would be pure noise on the wire.
        if not self._entrypoints:
            try:
                self._entrypoints = tuple(await self.client.list_entrypoints())
            except TraefikError as err:
                _LOGGER.debug("Could not read entrypoints: %s", err)

        metrics = Metrics()
        try:
            metrics = await self.client.get_metrics()
        except TraefikError as err:
            # The metrics endpoint is optional and often on a port that is
            # firewalled off. Losing it should not take the rest down.
            _LOGGER.debug("Could not read metrics: %s", err)

        return TraefikData(
            server=server,
            overview=overview,
            routers={router.name: router for router in routers},
            services={service.name: service for service in services},
            entrypoints=self._entrypoints,
            metrics=metrics,
        )
