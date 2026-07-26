"""Sensors for the Traefik integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from traefik import Router, TrafficStats

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TraefikConfigEntry, TraefikCoordinator, TraefikData
from .entity import TraefikEntity, TraefikRouterEntity, async_add_router_entities

type StateValue = int | float | str | datetime | None


@dataclass(frozen=True, kw_only=True)
class TraefikSensorDescription(SensorEntityDescription):
    """Describes an instance-level sensor."""

    value_fn: Callable[[TraefikData], StateValue]


@dataclass(frozen=True, kw_only=True)
class TraefikRouterSensorDescription(SensorEntityDescription):
    """Describes a router-level sensor.

    Router sensors get the whole snapshot alongside the router because the
    interesting numbers — traffic, certificate expiry — live in the metrics
    and have to be looked up through the router's service.
    """

    value_fn: Callable[[Router, TraefikData], StateValue]


def _nearest_expiry(data: TraefikData) -> datetime | None:
    """Return when the soonest-expiring certificate stops being valid."""
    certificate = data.metrics.nearest_expiry
    return certificate.not_after if certificate else None


def _router_expiry(router: Router, data: TraefikData) -> datetime | None:
    """Return when this route's own certificate expires."""
    certificate = data.certificate_for(router)
    return certificate.not_after if certificate else None


def _traffic(
    getter: Callable[[TrafficStats], StateValue],
) -> Callable[[Router, TraefikData], StateValue]:
    """Build a value function reading one counter off a route's service."""

    def _value(router: Router, data: TraefikData) -> StateValue:
        stats = data.traffic_for(router)
        return getter(stats) if stats is not None else None

    return _value


def _milliseconds(seconds: float | None) -> float | None:
    """Convert a duration to whole-ish milliseconds for display."""
    return None if seconds is None else round(seconds * 1000, 1)


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
    TraefikSensorDescription(
        key="hostnames",
        translation_key="hostnames",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.hostnames),
    ),
    TraefikSensorDescription(
        key="requests",
        translation_key="requests",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.metrics.totals().requests or None,
    ),
    TraefikSensorDescription(
        key="request_errors",
        translation_key="request_errors",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.metrics.totals().errors
        if d.metrics.entrypoints
        else None,
    ),
    TraefikSensorDescription(
        key="error_rate",
        translation_key="error_rate",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.metrics.totals().error_rate,
    ),
    TraefikSensorDescription(
        key="average_response_time",
        translation_key="average_response_time",
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        device_class=SensorDeviceClass.DURATION,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _milliseconds(d.metrics.totals().average_duration),
    ),
)

ROUTER_SENSORS: tuple[TraefikRouterSensorDescription, ...] = (
    TraefikRouterSensorDescription(
        key="status",
        translation_key="router_status",
        value_fn=lambda r, _: r.status or None,
    ),
    TraefikRouterSensorDescription(
        key="requests",
        translation_key="requests",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_traffic(lambda s: s.requests),
    ),
    TraefikRouterSensorDescription(
        key="request_errors",
        translation_key="request_errors",
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_traffic(lambda s: s.errors),
    ),
    TraefikRouterSensorDescription(
        key="error_rate",
        translation_key="error_rate",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_traffic(lambda s: s.error_rate),
    ),
    TraefikRouterSensorDescription(
        key="average_response_time",
        translation_key="average_response_time",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        device_class=SensorDeviceClass.DURATION,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_traffic(lambda s: _milliseconds(s.average_duration)),
    ),
    TraefikRouterSensorDescription(
        key="certificate_expiry",
        translation_key="certificate_expiry",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_router_expiry,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TraefikConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        TraefikInstanceSensor(coordinator, description)
        for description in INSTANCE_SENSORS
    )
    async_add_router_entities(
        coordinator,
        async_add_entities,
        lambda name: [
            TraefikRouterSensor(coordinator, name, description)
            for description in ROUTER_SENSORS
        ],
    )


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
    def native_value(self) -> StateValue:
        """Return the current value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        """Expose the detail behind the headline number.

        Only the sensors where the list is the point carry one — a count of
        hostnames is far less useful than the hostnames.
        """
        if (data := self.coordinator.data) is None:
            return None
        key = self.entity_description.key
        if key == "hostnames":
            return {"hostnames": list(data.hostnames)}
        if key == "open_connections":
            return {"by_entrypoint": dict(data.metrics.connections_by_entrypoint)}
        if key == "certificates":
            return {
                "certificates": [
                    {
                        "common_name": certificate.common_name,
                        "sans": list(certificate.sans),
                        "expires": certificate.not_after.isoformat(),
                        "days_remaining": certificate.days_remaining,
                    }
                    for certificate in sorted(
                        data.metrics.certificates, key=lambda c: c.not_after
                    )
                ]
            }
        if key == "entrypoints":
            return {
                "entry_points": {
                    entrypoint.name: entrypoint.address
                    for entrypoint in data.entrypoints
                }
            }
        return None


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
    def native_value(self) -> StateValue:
        """Return the current value, or ``None`` if the router is gone."""
        if (router := self.router) is None or self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(router, self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        """Expose what the route actually does, on its status sensor.

        Everything here is per-route configuration rather than a number, so it
        belongs on one entity instead of being repeated on all six.
        """
        if self.entity_description.key != "status":
            return None
        if (router := self.router) is None or (data := self.coordinator.data) is None:
            return None

        attributes: dict[str, object] = {
            "hostnames": list(router.hostnames),
            "rule": router.rule,
            "router": router.name,
            "service": router.service,
            "provider": router.provider,
            "priority": router.priority,
            "entry_points": ", ".join(router.entry_points) or None,
            "middlewares": ", ".join(router.middlewares) or None,
            "tls": router.tls,
        }

        if (service := data.service_for(router)) is not None:
            attributes["servers"] = [
                {"url": url, "status": status}
                for url, status in sorted(service.server_status.items())
            ]
            attributes["health_checked"] = service.has_health_check
        if (certificate := data.certificate_for(router)) is not None:
            attributes["certificate"] = certificate.common_name
        return attributes
