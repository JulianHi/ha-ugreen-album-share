"""Expose the shared albums in the Home Assistant media browser."""

from __future__ import annotations

from homeassistant.components.media_player import BrowseError, MediaClass, MediaType
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .api import Photo, UgreenShareError
from .const import DOMAIN
from .coordinator import UgreenAlbumCoordinator, async_get_coordinators
from .images import JPEG as IMAGE_MIME
from .view import image_path


async def async_get_media_source(hass: HomeAssistant) -> MediaSource:
    """Set up the media source."""
    return UgreenAlbumMediaSource(hass)


class UgreenAlbumMediaSource(MediaSource):
    """Albums are folders, photos are items. Identifier: '<uuid>' or '<uuid>/<photo id>'."""

    name = "UGREEN Albums"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve a photo to a (signed by HA) proxy URL."""
        album_uuid, _, photo_id = (item.identifier or "").partition("/")
        if album_uuid not in async_get_coordinators(self.hass) or not photo_id.isdigit():
            raise Unresolvable(f"Unknown photo {item.identifier}")
        return PlayMedia(image_path(album_uuid, int(photo_id), "full"), IMAGE_MIME)

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        """Browse albums or the photos of one album."""
        coordinators = async_get_coordinators(self.hass)
        if not item.identifier:
            return BrowseMediaSource(
                domain=DOMAIN,
                identifier=None,
                media_class=MediaClass.DIRECTORY,
                media_content_type=MediaType.IMAGE,
                title=self.name,
                can_play=False,
                can_expand=True,
                children_media_class=MediaClass.DIRECTORY,
                children=[
                    _album_node(album_uuid, coordinator)
                    for album_uuid, coordinator in coordinators.items()
                ],
            )

        album_uuid, _, photo_id = item.identifier.partition("/")
        if photo_id or (coordinator := coordinators.get(album_uuid)) is None:
            raise BrowseError(f"Unknown album {item.identifier}")
        try:
            photos = await coordinator.client.async_get_photos(force_refresh=True)
        except UgreenShareError as err:
            raise BrowseError(f"Album {coordinator.album_name} not available: {err}") from err

        node = _album_node(album_uuid, coordinator)
        node.children = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"{album_uuid}/{photo.id}",
                media_class=MediaClass.IMAGE,
                media_content_type=IMAGE_MIME,
                title=_photo_title(photo),
                can_play=True,
                can_expand=False,
                thumbnail=image_path(album_uuid, photo.id, "thumbnail"),
            )
            for photo in photos
        ]
        return node


def _photo_title(photo: Photo) -> str:
    """Date taken reads better than the (often uuid-like) file name."""
    if photo.taken:
        return dt_util.as_local(dt_util.utc_from_timestamp(photo.taken)).strftime("%Y-%m-%d %H:%M")
    return photo.file_name or str(photo.id)


def _album_node(album_uuid: str, coordinator: UgreenAlbumCoordinator) -> BrowseMediaSource:
    photos = coordinator.data or []
    return BrowseMediaSource(
        domain=DOMAIN,
        identifier=album_uuid,
        media_class=MediaClass.DIRECTORY,
        media_content_type=MediaType.IMAGE,
        title=coordinator.album_name,
        can_play=False,
        can_expand=True,
        children_media_class=MediaClass.IMAGE,
        thumbnail=image_path(album_uuid, photos[0].id, "thumbnail") if photos else None,
    )
