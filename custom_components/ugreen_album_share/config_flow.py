"""Config and options flow: add and remove any number of album share links."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME, CONF_URL, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    InvalidShareLink,
    ShareLink,
    UgreenShareClient,
    UgreenShareConnectionError,
    UgreenShareError,
    UgreenSharePasswordError,
)
from .const import CONF_ALBUMS, CONF_ROTATE_INTERVAL, DEFAULT_ROTATE_INTERVAL, DOMAIN, LOGGER

CONF_REMOVE = "remove"

ALBUM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
        vol.Optional(CONF_NAME): str,
    }
)


async def _async_album_from_input(
    hass: HomeAssistant, user_input: dict[str, Any], albums: list[dict[str, str]], verify_ssl: bool
) -> tuple[dict[str, str] | None, dict[str, str]]:
    """Validate a share link; returns (album, errors)."""
    try:
        link = ShareLink.parse(user_input[CONF_URL])
    except InvalidShareLink:
        return None, {CONF_URL: "invalid_url"}
    if any(ShareLink.parse(album[CONF_URL]).uuid == link.uuid for album in albums):
        return None, {CONF_URL: "already_configured"}

    client = UgreenShareClient(async_get_clientsession(hass, verify_ssl=verify_ssl), link)
    try:
        await client.async_get_photos()
    except UgreenSharePasswordError:
        return None, {"base": "password_protected"}
    except UgreenShareConnectionError:
        return None, {"base": "cannot_connect"}
    except UgreenShareError:
        return None, {"base": "invalid_share"}
    except Exception:  # noqa: BLE001
        LOGGER.exception("Unexpected error validating %s", link.url)
        return None, {"base": "unknown"}

    name = (user_input.get(CONF_NAME) or "").strip() or client.album_name or f"Album {link.share_id}"
    return {CONF_URL: link.url, CONF_NAME: name}, {}


class UgreenAlbumConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup asks for the first album."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the first share link."""
        errors: dict[str, str] = {}
        if user_input is not None:
            album, errors = await _async_album_from_input(self.hass, user_input, [], True)
            if album:
                return self.async_create_entry(
                    title="UGREEN Album Share",
                    data={},
                    options={
                        CONF_ALBUMS: [album],
                        CONF_ROTATE_INTERVAL: DEFAULT_ROTATE_INTERVAL,
                        CONF_VERIFY_SSL: True,
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(ALBUM_SCHEMA, user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> UgreenAlbumOptionsFlow:
        """Albums are managed in the options flow."""
        return UgreenAlbumOptionsFlow()


class UgreenAlbumOptionsFlow(OptionsFlow):
    """Menu to add albums, remove albums or change settings."""

    @property
    def _albums(self) -> list[dict[str, str]]:
        return list(self.config_entry.options.get(CONF_ALBUMS, []))

    def _save(self, **changes: Any) -> ConfigFlowResult:
        return self.async_create_entry(data={**self.config_entry.options, **changes})

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Main menu."""
        return self.async_show_menu(
            step_id="init", menu_options=["add_album", "remove_album", "settings"]
        )

    async def async_step_add_album(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add another share link."""
        errors: dict[str, str] = {}
        if user_input is not None:
            album, errors = await _async_album_from_input(
                self.hass,
                user_input,
                self._albums,
                self.config_entry.options.get(CONF_VERIFY_SSL, True),
            )
            if album:
                return self._save(**{CONF_ALBUMS: [*self._albums, album]})
        return self.async_show_form(
            step_id="add_album",
            data_schema=self.add_suggested_values_to_schema(ALBUM_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_remove_album(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove one or more albums."""
        if not self._albums:
            return self.async_abort(reason="no_albums")
        if user_input is not None:
            remove = set(user_input[CONF_REMOVE])
            return self._save(
                **{CONF_ALBUMS: [a for a in self._albums if a[CONF_URL] not in remove]}
            )
        options = [SelectOptionDict(value=a[CONF_URL], label=a[CONF_NAME]) for a in self._albums]
        return self.async_show_form(
            step_id="remove_album",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_REMOVE, default=[]): SelectSelector(
                        SelectSelectorConfig(options=options, multiple=True)
                    )
                }
            ),
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Rotation interval of the random photo and TLS verification."""
        if user_input is not None:
            return self._save(
                **{
                    CONF_ROTATE_INTERVAL: int(user_input[CONF_ROTATE_INTERVAL]),
                    CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
                }
            )
        options = self.config_entry.options
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ROTATE_INTERVAL,
                        default=options.get(CONF_ROTATE_INTERVAL, DEFAULT_ROTATE_INTERVAL),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=10, max=86400, step=1, unit_of_measurement="s", mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Required(
                        CONF_VERIFY_SSL, default=options.get(CONF_VERIFY_SSL, True)
                    ): BooleanSelector(),
                }
            ),
        )
