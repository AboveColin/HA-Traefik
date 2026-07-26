"""Sensors for the Traefik integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from traefik import Router

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TraefikConfigEntry, TraefikCoordinator, TraefikData
from .entity import TraefikEntity, TraefikRouterEntity


@dataclass(frozen=True, kw_only=True)
class TraefikSensorDescription(SensorEntityDescription):
    """Describes an instance-level sensor."""

    value_fn: Callable[[TraefikData], int | str | datetime | None]


@dataclass(frozen=True, kw_only=True)
class TraefikRouterSensorDescription(SensorEntityDescription):
    """Describes a router-level sensor."""

    value_fn: Callable[[Router], str | int | None]


def _nearest_expiry(data: TraefikData) -> datetime | None:
    """Return when the soonest-expiring certificate stops being valid."""
    certificate = data.metrics.nearest_expiry
    return certificate.not_after if certificate else None


INSTANCE_SENSORS: tuple[TraefikSensorDescription, ...] = (
    TraefikSensorDescription(
        key="http_routers",
        translation_key="http_routers",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.overview.http_routers.total,
    ),
    TraefikSensorDescription(
        key="http_router_errors",
        translation_key="http_router_errors",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.overview.http_routers.errors,
    ),
    TraefikSensorDescription(
        key="http_services",
        translation_key="http_services",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.overview.http_services.total,
    ),
    TraefikSensorDescription(
        key="http_service_errors",
        translation_key="http_service_errors",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.overview.http_services.errors,
    ),
    TraefikSensorDescription(
        key="http_middlewares",
        translation_key="http_middlewares",
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.overview.http_middlewares.total,
    ),
    TraefikSensorDescription(
        key="tcp_routers",
        translation_key="tcp_routers",
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.overview.tcp_routers.total,
    ),
    TraefikSensorDescription(
        key="udp_routers",
        translation_key="udp_routers",
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.overview.udp_routers.total,
    ),
    TraefikSensorDescription(
        key="certificates",
        translation_key="certificates",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.overview.certificates,
    ),
    TraefikSensorDescription(
        key="entrypoints",
        translation_key="entrypoints",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.entrypoints),
    ),
    TraefikSensorDescription(
        key="version",
        translation_key="version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.server.version,
    ),
    TraefikSensorDescription(
        key="started",
        translation_key="started",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.server.start_date,
    ),
    # Everything below comes from the Prometheus endpoint and stays unknown
    # unless one was configured.
    TraefikSensorDescription(
        key="open_connections",
        translation_key="open_connections",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.metrics.open_connections,
    ),
    TraefikSensorDescription(
        key="config_reloads",
        translation_key="config_reloads",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.metrics.config_reloads,
    ),
    TraefikSensorDescription(
        key="last_reload",
        translation_key="last_reload",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.metrics.last_reload,
    ),
    TraefikSensorDescription(
        key="certificate_expiry",
        translation_key="certificate_expiry",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_nearest_expiry,
    ),
)

ROUTER_SENSORS: tuple[TraefikRouterSensorDescription, ...] = (
    TraefikRouterSensorDescription(
        key="status",
        translation_key="router_status",
        value_fn=lambda r: r.status or None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TraefikConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        TraefikInstanceSensor(coordinator, description)
        for description in INSTANCE_SENSORS
    ]
    entities.extend(
        TraefikRouterSensor(coordinator, name, description)
        for name in coordinator.tracked_routers
        for description in ROUTER_SENSORS
    )
    async_add_entities(entities)


class TraefikInstanceSensor(TraefikEntity, SensorEntity):
    """A sensor describing the instance."""

    entity_description: TraefikSensorDescription

    def __init__(
        self, coordinator: TraefikCoordinator, description: TraefikSensorDescription
    ) -> None:
        """Set up the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | str | datetime | None:
        """Return the current value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class TraefikRouterSensor(TraefikRouterEntity, SensorEntity):
    """A sensor describing one router."""

    entity_description: TraefikRouterSensorDescription

    def __init__(
        self,
        coordinator: TraefikCoordinator,
        name: str,
        description: TraefikRouterSensorDescription,
    ) -> None:
        """Set up the sensor."""
        super().__init__(coordinator, name, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | int | None:
        """Return the current value, or ``None`` if the router is gone."""
        if (router := self.router) is None:
            return None
        return self.entity_description.value_fn(router)

    @property
    def extra_state_attributes(self) -> dict[str, str | int | bool | None] | None:
        """Expose what the router actually does."""
        if (router := self.router) is None:
            return None
        return {
            "rule": router.rule,
            "service": router.service,
            "provider": router.provider,
            "priority": router.priority,
            "entry_points": ", ".join(router.entry_points) or None,
            "middlewares": ", ".join(router.middlewares) or None,
            "tls": router.tls,
        }
