# UGREEN Album Share for Home Assistant

Brings **shared albums** (including smart albums) from a UGREEN NAS (UGOS Pro, "Photos" app) into Home Assistant – without exposing your whole photo library via SMB/WebDAV and without NAS credentials.

- **Media browser:** every album shows up under *Media → UGREEN Albums* as a folder with all its photos (newest first). The list is read live from the NAS, so new photos in an album appear right away.
- **Image entity per album:** `image.<album>_random_photo` shows a random photo and changes it at a configurable interval – great for picture-entity cards or wall tablets.
- **Any number of albums**, managed via *Configure*.
- **Access-code protected shares** are supported.

Photos are served through Home Assistant (proxy), so they also work when the browser cannot reach the NAS directly (e.g. when you are away from home). All photos are delivered as JPEG (or PNG), including HEIC and WebP originals, so simple clients like photo frames can show them too.

## Using the albums elsewhere (slideshows, photo frames)

Any client that browses Home Assistant media sources can use the albums, e.g. the idle-screen slideshow of an Echo Show running [techo5](https://github.com/HuskerMinion/techo5). Media source IDs:

| What | Media source ID |
|---|---|
| All albums | `media-source://ugreen_album_share` (no trailing slash – Home Assistant rejects `…/`) |
| One album | `media-source://ugreen_album_share/<uuid>` (the `uuid` from the share link) |

The album uuid is also shown in the address bar when you open an album in the media browser.

> [!WARNING]
> **Disclaimer – use at your own risk.**
> This is an unofficial community project. It is not affiliated with, endorsed by or supported by UGREEN. It uses the undocumented API of the UGOS Pro album share web page, which may change or break with any NAS update. The software is provided "as is", without warranty of any kind (see [LICENSE](LICENSE)). The authors are not responsible for any damage, data loss or exposure of private photos resulting from its use.

> [!NOTE]
> **Written by AI.** The code and documentation of this integration were written by [Claude](https://claude.ai) (Anthropic's AI assistant, via Claude Code), guided, reviewed and tested by a human.

## Installation via HACS

1. HACS → ⋮ → *Custom repositories* → add the URL of this repository, type **Integration**.
2. Install "UGREEN Album Share" and restart Home Assistant.
3. *Settings → Devices & services → Add integration → UGREEN Album Share*.

### Manual installation

Copy `custom_components/ugreen_album_share` into the `custom_components` folder of your Home Assistant configuration and restart.

## Creating a share link

In the UGREEN Photos app (web or mobile), open an album → **Share** → copy the link. It looks like this:

```
https://<nas>/photo/share/?id=2&pagetype=share&uuid=0d7328f5-....
```

- If the share is protected by an **access code**, enter it in the "Access code" field (otherwise leave it empty).
- The share should have **no expiry date**, otherwise the album disappears once it expires.
- Home Assistant must be able to reach the address in the link.

## Configuration

When adding the integration you are asked for the first album link. Afterwards use *UGREEN Album Share → Configure*:

| Menu entry | Purpose |
|---|---|
| Add album | add another share link (access code and name optional, the name defaults to the album name on the NAS) |
| Edit album | change the name or access code of an album (e.g. after the code was changed on the NAS) |
| Remove albums | remove one or more albums (including their device and entity) |
| Settings | interval of the random photo, SSL certificate verification (disable for self-signed certificates) |

## Example: slideshow card

```yaml
type: picture-entity
entity: image.laura_random_photo
show_state: false
show_name: false
```

The entity attributes contain `photo_id`, `file_name`, `taken` and `photo_count`.

## How it works

The integration uses the same API as the share web page of the NAS:

1. `POST /ugreen/v5/photo/share/white/verify` → anonymous token (valid for 24 h, renewed automatically).
   For protected shares the NAS instead returns an RSA public key (`x-rsa-token`); the access code is encrypted with it and sent to `POST …/white/password`, which returns the token.
   The NAS rate limits access code attempts (HTTP 429, wait about a minute).
2. `GET /ugreen/v5/photo/share/external/detail` → list of photos
3. `GET /ugreen/v5/photo/share/external/stream?id=…&size_type=…` → photo (1 = thumbnail, 3 = full size as WebP, 0 = original)

The access code is stored in the Home Assistant configuration (`.storage`), like passwords of other integrations. With the token, the NAS only serves photos that are part of the shared album.

Tested with UGOS Pro, share web app `com.ugreen.album-share` version 324, and Home Assistant 2026.2.

## License

[MIT](LICENSE)
