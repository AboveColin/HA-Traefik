"""Binary sensors for the Traefik integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from traefik import Router

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TraefikConfigEntry, TraefikCoordinator, TraefikData
from .entity import TraefikEntity, TraefikRouterEntity


@dataclass(frozen=True, kw_only=True)
class TraefikBinarySensorDescription(BinarySensorEntityDescription):
    """Describes an instance-level binary sensor."""

    value_fn: Callable[[TraefikData], bool | None]


@dataclass(frozen=True, kw_only=True)
class TraefikRouterBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a router-level binary sensor."""

    value_fn: Callable[[Router], bool | None]


def _configuration_problem(data: TraefikData) -> bool:
    """Return whether Traefik rejected any part of the configuration."""
    overview = data.overview
    return any(
        section.errors
        for section in (
            overview.http_routers,
            overview.http_services,
            overview.http_middlewares,
            overview.tcp_routers,
            overview.tcp_services,
            overview.tcp_middlewares,
            overview.udp_routers,
            overview.udp_services,
        )
    )


def _backend_unhealthy(data: TraefikData) -> bool | None:
    """Return whether any actively probed backend server is down.

    Traefik only ever reports a server as down when that service has a
    ``loadBalancer.healthCheck`` configured. Where none do, this is unknown
    rather than "everything is fine" — otherwise a switched-off backend would
    read as healthy.
    """
    probed = [
        service for service in data.services.values() if service.has_health_check
    ]
    if not probed:
        return None
    return any(service.all_servers_up is False for service in probed)


INSTANCE_BINARY_SENSORS: tuple[TraefikBinarySensorDescription, ...] = (
    TraefikBinarySensorDescription(
        key="configuration_problem",
        translation_key="configuration_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_configuration_problem,
    ),
    TraefikBinarySensorDescription(
        key="backend_unhealthy",
        translation_key="backend_unhealthy",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_backend_unhealthy,
    ),
)

ROUTER_BINARY_SENSORS: tuple[TraefikRouterBinarySensorDescription, ...] = (
    TraefikRouterBinarySensorDescription(
        key="problem",
        translation_key="router_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda r: None if not r.status else not r.enabled,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TraefikConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors from a config entry."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        TraefikInstanceBinarySensor(coordinator, description)
        for description in INSTANCE_BINARY_SENSORS
    ]
    entities.extend(
        TraefikRouterBinarySensor(coordinator, name, description)
        for name in coordinator.tracked_routers
        for description in ROUTER_BINARY_SENSORS
    )
    async_add_entities(entities)


class TraefikInstanceBinarySensor(TraefikEntity, BinarySensorEntity):
    """A binary sensor describing the instance."""

    entity_description: TraefikBinarySensorDescription

    def __init__(
        self,
        coordinator: TraefikCoordinator,
        description: TraefikBinarySensorDescription,
    ) -> None:
        """Set up the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the current state, or ``None`` when it is not knowable."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class TraefikRouterBinarySensor(TraefikRouterEntity, BinarySensorEntity):
    """A binary sensor describing one router."""

    entity_description: TraefikRouterBinarySensorDescription

    def __init__(
        self,
        coordinator: TraefikCoordinator,
        name: str,
        description: TraefikRouterBinarySensorDescription,
    ) -> None:
        """Set up the binary sensor."""
        super().__init__(coordinator, name, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the current state, or ``None`` if the router is gone."""
        if (router := self.router) is None:
            return None
        return self.entity_description.value_fn(router)
