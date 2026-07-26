"""Shared entity bases and the ``DeviceInfo`` both platforms use."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from traefik import Router
from yarl import URL

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
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


def router_device_info(coordinator: TraefikCoordinator, name: str) -> DeviceInfo:
    """Return the device describing one router.

    The device is named after the hostname it serves rather than the internal
    router name, because ``git.example.com`` says what broke and
    ``git-svc@file`` does not. Routers that match on something other than a
    host keep their configured name.
    """
    router = coordinator.data.routers.get(name) if coordinator.data else None
    hostnames = router.hostnames if router else ()
    configuration_url = None
    if hostnames:
        configuration_url = f"{'https' if router and router.tls else 'http'}://{hostnames[0]}"

    return DeviceInfo(
        identifiers={(DOMAIN, f"{coordinator.config_entry.entry_id}_{name}")},
        entry_type=DeviceEntryType.SERVICE,
        manufacturer=MANUFACTURER,
        model="Route",
        name=hostnames[0] if hostnames else name,
        configuration_url=configuration_url,
        via_device=(DOMAIN, coordinator.config_entry.entry_id),
    )


@callback
def async_add_router_entities(
    coordinator: TraefikCoordinator,
    async_add_entities: AddEntitiesCallback,
    factory: Callable[[str], Iterable[Entity]],
) -> None:
    """Add entities per router, now and for routers that appear later.

    With every router tracked, the set is whatever Traefik currently serves,
    so a newly deployed host has to arrive on a poll rather than waiting for
    the user to reload the integration.
    """
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new = [name for name in coordinator.tracked_routers if name not in known]
        if not new:
            return
        known.update(new)
        async_add_entities(
            entity for name in new for entity in factory(name)
        )

    _add_new()
    coordinator.config_entry.async_on_unload(coordinator.async_add_listener(_add_new))


class TraefikRouterEntity(CoordinatorEntity[TraefikCoordinator]):
    """Base for entities describing one router."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TraefikCoordinator, name: str, key: str) -> None:
        """Set up the entity."""
        super().__init__(coordinator)
        self._router_name = name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{name}_{key}"
        self._attr_device_info = router_device_info(coordinator, name)

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
