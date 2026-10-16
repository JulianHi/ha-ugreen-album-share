"""Image entity showing a random photo of each album."""

from __future__ import annotations

import random
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import SIZE_FULL, Photo, UgreenShareError
from .const import DOMAIN, LOGGER
from .coordinator import UgreenAlbumConfigEntry, UgreenAlbumCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UgreenAlbumConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """One random photo entity per album."""
    async_add_entities(
        UgreenAlbumRandomImage(hass, coordinator) for coordinator in entry.runtime_data.values()
    )


class UgreenAlbumRandomImage(CoordinatorEntity[UgreenAlbumCoordinator], ImageEntity):
    """Picks another random photo on every coordinator update."""

    _attr_has_entity_name = True
    _attr_translation_key = "random_photo"
    _attr_content_type = "image/webp"

    def __init__(self, hass: HomeAssistant, coordinator: UgreenAlbumCoordinator) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        link = coordinator.client.link
        self._attr_unique_id = f"{link.uuid}_random_photo"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, link.uuid)},
            name=coordinator.album_name,
            manufacturer="UGREEN",
            model="Geteiltes Album",
            configuration_url=link.url,
            entry_type=DeviceEntryType.SERVICE,
        )
        self._photo: Photo | None = None
        self._image: tuple[int, bytes] | None = None
        self._pick_photo()

    def _pick_photo(self) -> None:
        photos = self.coordinator.data or []
        candidates = [p for p in photos if p != self._photo] or photos
        if candidates:
            self._photo = random.choice(candidates)
            self._attr_image_last_updated = dt_util.utcnow()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._pick_photo()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Available once a photo was picked."""
        return super().available and self._photo is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Details of the current photo."""
        if self._photo is None:
            return None
        return {
            "photo_id": self._photo.id,
            "file_name": self._photo.file_name,
            "taken": dt_util.utc_from_timestamp(self._photo.taken).isoformat()
            if self._photo.taken
            else None,
            "photo_count": len(self.coordinator.data or []),
        }

    async def async_image(self) -> bytes | None:
        """Return the current photo, downloaded once per pick."""
        if self._photo is None:
            return None
        if self._image and self._image[0] == self._photo.id:
            return self._image[1]
        try:
            content_type, body = await self.coordinator.client.async_get_image(self._photo.id, SIZE_FULL)
        except UgreenShareError as err:
            LOGGER.warning("Could not load photo %s: %s", self._photo.id, err)
            return None
        self._attr_content_type = content_type
        self._image = (self._photo.id, body)
        return body
