"""Shared entity bases and the ``DeviceInfo`` both platforms use."""

from __future__ import annotations

from traefik import Router
from yarl import URL

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import TraefikCoordinator


def instance_device_info(coordinator: TraefikCoordinator) -> DeviceInfo:
    """Return the device describing the instance as a whole."""
    url = coordinator.config_entry.data.get("url", "")
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        entry_type=DeviceEntryType.SERVICE,
        manufacturer=MANUFACTURER,
        model="Traefik Proxy",
        name=URL(url).host or DOMAIN,
        configuration_url=url or None,
        sw_version=coordinator.data.server.version if coordinator.data else None,
    )


class TraefikEntity(CoordinatorEntity[TraefikCoordinator]):
    """Base for entities describing the instance as a whole."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TraefikCoordinator, key: str) -> None:
        """Set up the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = instance_device_info(coordinator)


class TraefikRouterEntity(CoordinatorEntity[TraefikCoordinator]):
    """Base for entities describing one router."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TraefikCoordinator, name: str, key: str) -> None:
        """Set up the entity."""
        super().__init__(coordinator)
        self._router_name = name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{name}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.config_entry.entry_id}_{name}")},
            entry_type=DeviceEntryType.SERVICE,
            manufacturer=MANUFACTURER,
            model="Router",
            name=name,
            via_device=(DOMAIN, coordinator.config_entry.entry_id),
        )

    @property
    def router(self) -> Router | None:
        """Return this router's latest state, if it is still configured."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.routers.get(self._router_name)

    @property
    def available(self) -> bool:
        """A router that vanished from the configuration is unavailable."""
        return super().available and self.router is not None
