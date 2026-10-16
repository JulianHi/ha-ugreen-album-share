"""Client for shared photo albums on a UGREEN NAS (UGOS Pro)."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit

import aiohttp
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.serialization import load_pem_public_key

API_PATH = "/ugreen/v5/photo/share"
PAGE_SIZE = 1000
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
# Renew the share token this many seconds before it expires (it lives 24 h).
TOKEN_MARGIN = 300
# How long a fetched photo list is reused before asking the NAS again.
LIST_CACHE_SECONDS = 600

SIZE_ORIGINAL = 0
SIZE_THUMBNAIL = 1
SIZE_FULL = 3  # full resolution, delivered as WebP (also for HEIC originals)

ERROR_WRONG_PASSWORD = 10056

# Tokens shared between client instances (validation in the config flow, reloads), so a
# protected share is not unlocked again each time: the NAS rate limits code logins.
_TOKENS: dict[tuple[str, int, str, str | None], tuple[str, float]] = {}


class UgreenShareError(Exception):
    """Generic error talking to the share API."""


class UgreenShareConnectionError(UgreenShareError):
    """The NAS could not be reached."""


class UgreenSharePasswordRequired(UgreenShareError):
    """The share is protected by an access code, but none was given."""


class UgreenShareInvalidPassword(UgreenShareError):
    """The access code was rejected."""


class UgreenShareRateLimited(UgreenShareError):
    """Too many attempts, the NAS asks to wait (usually 60 s)."""


class InvalidShareLink(UgreenShareError):
    """The given URL is not a UGREEN album share link."""


@dataclass(frozen=True)
class ShareLink:
    """Parsed share link, e.g. https://nas/photo/share/?id=2&pagetype=share&uuid=..."""

    base_url: str
    share_id: int
    uuid: str

    @classmethod
    def parse(cls, url: str) -> ShareLink:
        """Parse a share link as copied from the UGREEN photo app."""
        parts = urlsplit(url.strip())
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise InvalidShareLink(url)
        query = parse_qs(parts.query)
        if "uuid" not in query and "?" in parts.fragment:
            query = parse_qs(parts.fragment.split("?", 1)[1])
        try:
            share_id = int(query["id"][0])
            uuid = query["uuid"][0]
        except (KeyError, IndexError, ValueError) as err:
            raise InvalidShareLink(url) from err
        return cls(f"{parts.scheme}://{parts.netloc}", share_id, uuid)

    @property
    def url(self) -> str:
        """Link to the share web page."""
        return (
            f"{self.base_url}/photo/share/"
            f"?id={self.share_id}&pagetype=share&uuid={self.uuid}"
        )


@dataclass(frozen=True)
class Photo:
    """A single photo of a shared album."""

    id: int
    file_name: str
    taken: int
    width: int
    height: int


def _decode_json(body: bytes) -> dict[str, Any]:
    try:
        return json.loads(body)
    except ValueError as err:
        raise UgreenShareError("Unexpected response from NAS") from err


def _encrypt_password(rsa_token: str, password: str) -> str:
    """Encrypt the access code like the share page (JSEncrypt, RSA PKCS#1 v1.5)."""
    key = load_pem_public_key(base64.b64decode(rsa_token))
    return base64.b64encode(key.encrypt(password.encode(), PKCS1v15())).decode()


def _token_expiry(token: str) -> float:
    """Read the exp claim of the (JWT) share token."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except (IndexError, KeyError, ValueError, TypeError):
        return time.time() + 3600


class UgreenShareClient:
    """Access one shared album without logging in, like the share web page does."""

    def __init__(
        self, session: aiohttp.ClientSession, link: ShareLink, password: str | None = None
    ) -> None:
        self._session = session
        self.link = link
        self._password = password
        self.album_name: str | None = None
        self._token_key = (link.base_url, link.share_id, link.uuid, password)
        self._photos: list[Photo] = []
        self._photos_fetched = 0.0

    async def _call(
        self, method: str, path: str, *, headers: dict[str, str] | None = None, **kwargs: Any
    ) -> tuple[aiohttp.ClientResponse, bytes]:
        try:
            response = await self._session.request(
                method,
                f"{self.link.base_url}{API_PATH}{path}",
                headers={"api-version": "3", **(headers or {})},
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            )
            body = await response.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UgreenShareConnectionError(str(err) or type(err).__name__) from err
        if response.status == 429:
            raise UgreenShareRateLimited("Too many requests")
        if response.status != 200:
            raise UgreenShareConnectionError(f"HTTP {response.status}")
        return response, body

    async def _async_token(self, force: bool = False) -> str:
        cached = _TOKENS.get(self._token_key)
        if not force and cached and time.time() < cached[1] - TOKEN_MARGIN:
            return cached[0]
        response, body = await self._call(
            "POST",
            "/white/verify",
            json={"id": self.link.share_id, "operation_type": 0, "uuid": self.link.uuid},
        )
        payload = _decode_json(body)
        if payload.get("code") != 200:
            raise UgreenShareError(payload.get("msg") or "Share not available")
        if (payload.get("data") or {}).get("has_pass_word"):
            response, payload = await self._async_login(response.headers.get("x-rsa-token"))
        token = response.headers.get("x-photo-external-token")
        if not token:
            raise UgreenShareError("NAS did not return a share token")
        _TOKENS[self._token_key] = (token, _token_expiry(token))
        return token

    async def _async_login(
        self, rsa_token: str | None
    ) -> tuple[aiohttp.ClientResponse, dict[str, Any]]:
        """Unlock a protected share with the access code."""
        if not self._password:
            raise UgreenSharePasswordRequired("Share is protected by an access code")
        if not rsa_token:
            raise UgreenShareError("NAS did not return an encryption key")
        try:
            encrypted = _encrypt_password(rsa_token, self._password)
        except ValueError as err:
            raise UgreenShareError(f"Invalid encryption key from NAS: {err}") from err
        response, body = await self._call(
            "POST", "/white/password", json={"share_id": self.link.share_id, "password": encrypted}
        )
        payload = _decode_json(body)
        if payload.get("code") == ERROR_WRONG_PASSWORD or (
            payload.get("code") == 200 and not (payload.get("data") or {}).get("permit")
        ):
            raise UgreenShareInvalidPassword("Access code was rejected")
        if payload.get("code") != 200:
            raise UgreenShareError(payload.get("msg") or "Could not unlock share")
        return response, payload

    async def async_get_photos(self, force_refresh: bool = False) -> list[Photo]:
        """Return all photos of the album, newest first."""
        if (
            not force_refresh
            and self._photos_fetched
            and time.monotonic() - self._photos_fetched < LIST_CACHE_SECONDS
        ):
            return self._photos

        for attempt in range(2):
            token = await self._async_token(force=attempt > 0)
            items: list[dict[str, Any]] = []
            while True:
                _, body = await self._call(
                    "GET",
                    "/external/detail",
                    params={"limit": PAGE_SIZE, "offset": len(items), "share_id": self.link.share_id},
                    headers={"x-photo-external-token": token},
                )
                payload = _decode_json(body)
                if payload.get("code") != 200:
                    break
                data = payload.get("data") or {}
                page = data.get("list") or []
                items.extend(page)
                if not page or len(items) >= data.get("total", 0):
                    self.album_name = data.get("name") or self.album_name
                    self._photos = sorted(
                        (
                            Photo(
                                id=item["picture_id"],
                                file_name=item.get("file_name", ""),
                                taken=item.get("create_time_utc") or 0,
                                width=item.get("width") or 0,
                                height=item.get("height") or 0,
                            )
                            for item in items
                        ),
                        key=lambda photo: photo.taken,
                        reverse=True,
                    )
                    self._photos_fetched = time.monotonic()
                    return self._photos
        raise UgreenShareError(payload.get("msg") or "Could not list album")

    async def async_get_image(self, photo_id: int, size: int = SIZE_FULL) -> tuple[str, bytes]:
        """Download one photo, returns (content type, bytes)."""
        for attempt in range(2):
            token = await self._async_token(force=attempt > 0)
            response, body = await self._call(
                "GET",
                "/external/stream",
                params={"id": photo_id, "size_type": size, "file_type": 0, "external_token": token},
            )
            # Errors (expired token, photo not in share, ...) come back as JSON.
            if not response.content_type.startswith("application/json"):
                return response.content_type, body
            message = _decode_json(body).get("msg")
        raise UgreenShareError(message or f"Could not load photo {photo_id}")
