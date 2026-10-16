"""HTTP proxy serving album photos to the Home Assistant frontend."""

from __future__ import annotations

from aiohttp import web

from homeassistant.components.http import KEY_HASS, HomeAssistantView

from .api import (
    SIZE_FULL,
    SIZE_ORIGINAL,
    SIZE_THUMBNAIL,
    UgreenShareConnectionError,
    UgreenShareError,
)
from .const import DOMAIN, LOGGER
from .coordinator import async_get_coordinators

SIZES = {"thumbnail": SIZE_THUMBNAIL, "full": SIZE_FULL, "original": SIZE_ORIGINAL}


def image_path(album_uuid: str, photo_id: int, size: str) -> str:
    """Path of a photo in the proxy (needs auth or a signed path)."""
    return f"/api/{DOMAIN}/{album_uuid}/{photo_id}/{size}"


class UgreenAlbumImageView(HomeAssistantView):
    """Proxy photos so they also work when the NAS is not reachable from the browser."""

    url = f"/api/{DOMAIN}/{{album_uuid}}/{{photo_id}}/{{size}}"
    name = f"api:{DOMAIN}:image"

    async def get(
        self, request: web.Request, album_uuid: str, photo_id: str, size: str
    ) -> web.Response:
        """Return one photo; the NAS itself only serves photos of the share."""
        coordinator = async_get_coordinators(request.app[KEY_HASS]).get(album_uuid)
        if coordinator is None or size not in SIZES or not photo_id.isdigit():
            return web.Response(status=404)
        try:
            content_type, body = await coordinator.client.async_get_image(int(photo_id), SIZES[size])
        except UgreenShareConnectionError as err:
            LOGGER.debug("NAS not reachable for photo %s: %s", photo_id, err)
            return web.Response(status=502)
        except UgreenShareError as err:
            LOGGER.debug("Could not load photo %s: %s", photo_id, err)
            return web.Response(status=404)
        return web.Response(
            body=body, content_type=content_type, headers={"Cache-Control": "private, max-age=86400"}
        )
