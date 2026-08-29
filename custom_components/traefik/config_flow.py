"""Config and options flow for the Traefik integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from traefik import (
    TraefikAuthenticationError,
    TraefikClient,
    TraefikConnectionError,
    TraefikError,
)
import voluptuous as vol
from yarl import URL

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_METRICS_URL,
    CONF_ROUTERS,
    CONF_TRACK_ALL,
    CONF_VERIFY_SSL,
    DEFAULT_TRACK_ALL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# A bare `str` renders the secret in clear text in the config form. TextSelector
# with type PASSWORD makes the browser treat it as a password field.
_SECRET = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Optional(CONF_USERNAME): str,
        vol.Optional(CONF_PASSWORD): _SECRET,
        vol.Optional(CONF_METRICS_URL): str,
        vol.Optional(CONF_VERIFY_SSL, default=True): bool,
    }
)


def _normalise_url(raw: str) -> str:
    """Accept what people paste: bare hosts, trailing slashes, API paths."""
    candidate = raw.strip().rstrip("/")
    if not candidate.startswith(("http://", "https://")):
        candidate = f"http://{candidate}"
    url = URL(candidate)
    # The dashboard lives at /dashboard/ and the API browser at /api; pasting
    # either is the obvious mistake, so strip it rather than 404 later.
    path = url.path.rstrip("/")
    for suffix in ("/dashboard", "/api/overview", "/api"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    return str(url.with_path(path)).rstrip("/")


def _label(url: str) -> str:
    """Return a short host:port label for an address."""
    parsed = URL(url)
    host = parsed.host or url
    return f"{host}:{parsed.port}" if parsed.port else host


class TraefikConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setting up a Traefik instance."""

    VERSION = 1

    def __init__(self) -> None:
        """Set up the flow."""
        self._reauth_entry: ConfigEntry | None = None

    async def _async_validate(self, data: dict[str, Any]) -> str | None:
        """Return an error key for the given settings, or ``None`` if they work."""
        verify_ssl = data.get(CONF_VERIFY_SSL, True)
        client = TraefikClient(
            data[CONF_URL],
            username=data.get(CONF_USERNAME) or None,
            password=data.get(CONF_PASSWORD) or None,
            metrics_url=data.get(CONF_METRICS_URL) or None,
            session=async_get_clientsession(self.hass, verify_ssl=verify_ssl),
            verify_ssl=verify_ssl,
        )
        try:
            await client.get_version()
            await client.get_overview()
        except TraefikAuthenticationError:
            return "invalid_auth"
        except TraefikConnectionError:
            return "cannot_connect"
        except TraefikError:
            return "invalid_response"
        except Exception:  # noqa: BLE001 - the flow must never leave a traceback in the UI
            _LOGGER.exception("Unexpected error validating the Traefik connection")
            return "unknown"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = dict(user_input)
            data[CONF_URL] = _normalise_url(data[CONF_URL])
            if metrics := data.get(CONF_METRICS_URL):
                data[CONF_METRICS_URL] = _normalise_url(metrics)

            error = await self._async_validate(data)
            if error is None:
                await self.async_set_unique_id(_label(data[CONF_URL]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=_label(data[CONF_URL]),
                    data=data,
                    options={CONF_ROUTERS: []},
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start re-authentication after Traefik started refusing us."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for credentials again."""
        errors: dict[str, str] = {}
        entry = self._reauth_entry
        assert entry is not None

        if user_input is not None:
            data = {**entry.data, **user_input}
            error = await self._async_validate(data)
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates=dict(user_input)
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_USERNAME): str,
                    vol.Optional(CONF_PASSWORD): _SECRET,
                }
            ),
            description_placeholders={"url": entry.data[CONF_URL]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TraefikOptionsFlow:
        """Return the options flow."""
        return TraefikOptionsFlow()


class TraefikOptionsFlow(OptionsFlow):
    """Let the user choose which routers to track."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the router picker."""
        if user_input is not None:
            # The picker is meaningless while everything is tracked, and a
            # stale selection left behind would silently take effect the
            # moment the switch is turned off again.
            if user_input.get(CONF_TRACK_ALL):
                user_input = {**user_input, CONF_ROUTERS: []}
            return self.async_create_entry(data=user_input)

        # Importing here keeps the platform-independent flow module free of a
        # circular import with the package __init__.
        from . import build_client  # noqa: PLC0415

        client = build_client(self.hass, self.config_entry)
        try:
            routers = await client.list_routers()
        except TraefikError:
            return self.async_abort(reason="cannot_connect")

        selected = self.config_entry.options.get(CONF_ROUTERS, [])
        # Keep any already-tracked router in the list even if it dropped out of
        # the configuration, so saving the form does not silently untrack it.
        choices = sorted({router.name for router in routers} | set(selected))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TRACK_ALL,
                        default=self.config_entry.options.get(
                            CONF_TRACK_ALL, DEFAULT_TRACK_ALL
                        ),
                    ): bool,
                    vol.Optional(CONF_ROUTERS, default=selected): SelectSelector(
                        SelectSelectorConfig(
                            options=choices,
                            multiple=True,
                            mode=SelectSelectorMode.DROPDOWN,
                            custom_value=True,
                            sort=True,
                        )
                    )
                }
            ),
        )
