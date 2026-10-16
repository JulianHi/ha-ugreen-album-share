"""Turn photos from the NAS into JPEG or PNG.

The NAS labels its renditions image/webp, but sends JPEG, PNG or WebP depending on the
photo. Browsers cope with all of them, but simpler clients (e.g. photo frames using the
media source) often only decode JPEG and PNG.
"""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError

from .const import LOGGER

JPEG = "image/jpeg"
PNG = "image/png"
JPEG_QUALITY = 90


def sniff_content_type(body: bytes) -> str | None:
    """Content type by the file's magic bytes."""
    if body[:3] == b"\xff\xd8\xff":
        return JPEG
    if body[:8] == b"\x89PNG\r\n\x1a\n":
        return PNG
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    if body[4:8] == b"ftyp":
        return "image/heif"
    return None


def to_jpeg_or_png(body: bytes, content_type: str) -> tuple[str, bytes]:
    """Return JPEG and PNG unchanged, re-encode anything else as JPEG (blocking, run in executor)."""
    kind = sniff_content_type(body)
    if kind in (JPEG, PNG):
        return kind, body
    try:
        with Image.open(io.BytesIO(body)) as image:
            out = io.BytesIO()
            image.convert("RGB").save(out, "JPEG", quality=JPEG_QUALITY)
    except (UnidentifiedImageError, OSError) as err:
        LOGGER.debug("Could not convert %s photo to JPEG: %s", kind or content_type, err)
        return kind or content_type, body
    return JPEG, out.getvalue()
