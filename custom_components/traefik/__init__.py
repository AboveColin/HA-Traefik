"""The Traefik integration."""

from __future__ import annotations

from traefik import TraefikClient

from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_METRICS_URL, CONF_VERIFY_SSL
from .coordinator import TraefikConfigEntry, TraefikCoordinator
from .entity import instance_device_info

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


def build_client(hass: HomeAssistant, entry: TraefikConfigEntry) -> TraefikClient:
    """Build a client from a config entry."""
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, True)
    return TraefikClient(
        entry.data[CONF_URL],
        username=entry.data.get(CONF_USERNAME) or None,
        password=entry.data.get(CONF_PASSWORD) or None,
        metrics_url=entry.data.get(CONF_METRICS_URL) or None,
        session=async_get_clientsession(hass, verify_ssl=verify_ssl),
        verify_ssl=verify_ssl,
    )


async def async_setup_entry(hass: HomeAssistant, entry: TraefikConfigEntry) -> bool:
    """Set up a Traefik config entry."""
    coordinator = TraefikCoordinator(hass, entry, build_client(hass, entry))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Register the instance device before the platforms run. Router devices
    # point at it with via_device, and whichever platform loads first would
    # otherwise reference a device that does not exist yet.
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **instance_device_info(coordinator)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TraefikConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: TraefikConfigEntry) -> None:
    """Reload when the tracked-router selection changes."""
    await hass.config_entries.async_reload(entry.entry_id)
