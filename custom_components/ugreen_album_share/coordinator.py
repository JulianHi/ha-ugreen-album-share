"""Coordinator keeping the photo list of one shared album."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Photo, UgreenShareClient, UgreenShareError
from .const import DOMAIN, LOGGER

type UgreenAlbumConfigEntry = ConfigEntry[dict[str, UgreenAlbumCoordinator]]


class UgreenAlbumCoordinator(DataUpdateCoordinator[list[Photo]]):
    """Fetches the photo list; every update also rotates the random photo entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: UgreenAlbumConfigEntry,
        client: UgreenShareClient,
        album_name: str,
        interval: int,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {album_name}",
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.album_name = album_name

    async def _async_update_data(self) -> list[Photo]:
        try:
            return await self.client.async_get_photos()
        except UgreenShareError as err:
            raise UpdateFailed(f"Album {self.album_name}: {err}") from err


def async_get_coordinators(hass: HomeAssistant) -> dict[str, UgreenAlbumCoordinator]:
    """All albums of loaded config entries, keyed by share uuid."""
    coordinators: dict[str, UgreenAlbumCoordinator] = {}
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            coordinators.update(entry.runtime_data)
    return coordinators
