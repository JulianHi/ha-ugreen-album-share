"""UGREEN Album Share: shared UGREEN NAS photo albums as Home Assistant media."""

from __future__ import annotations

import asyncio

from homeassistant.const import CONF_NAME, CONF_URL, CONF_VERIFY_SSL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import ShareLink, UgreenShareClient
from .const import CONF_ALBUMS, CONF_ROTATE_INTERVAL, DEFAULT_ROTATE_INTERVAL, DOMAIN
from .coordinator import UgreenAlbumConfigEntry, UgreenAlbumCoordinator
from .view import UgreenAlbumImageView

PLATFORMS = [Platform.IMAGE]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the image proxy used by the media browser."""
    hass.http.register_view(UgreenAlbumImageView())
    return True


async def async_setup_entry(hass: HomeAssistant, entry: UgreenAlbumConfigEntry) -> bool:
    """Set up one coordinator per configured album."""
    session = async_get_clientsession(hass, verify_ssl=entry.options.get(CONF_VERIFY_SSL, True))
    interval = entry.options.get(CONF_ROTATE_INTERVAL, DEFAULT_ROTATE_INTERVAL)

    coordinators: dict[str, UgreenAlbumCoordinator] = {}
    for album in entry.options.get(CONF_ALBUMS, []):
        client = UgreenShareClient(session, ShareLink.parse(album[CONF_URL]))
        coordinators[client.link.uuid] = UgreenAlbumCoordinator(
            hass, entry, client, album[CONF_NAME], interval
        )
    # An unreachable album only makes its own entity unavailable.
    await asyncio.gather(*(c.async_refresh() for c in coordinators.values()))
    entry.runtime_data = coordinators

    _async_remove_stale_devices(hass, entry, coordinators)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: UgreenAlbumConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: UgreenAlbumConfigEntry) -> None:
    """Albums or settings changed in the options flow."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_remove_stale_devices(
    hass: HomeAssistant, entry: UgreenAlbumConfigEntry, coordinators: dict[str, UgreenAlbumCoordinator]
) -> None:
    """Remove devices (and their entities) of albums that were removed."""
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        if not any(ident[1] in coordinators for ident in device.identifiers if ident[0] == DOMAIN):
            registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
