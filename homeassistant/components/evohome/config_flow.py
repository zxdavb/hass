"""Config flow to configure the evohome integration."""

from datetime import timedelta
from functools import partial
import logging
from typing import Any, Final

import evohomeasync2 as evo
import voluptuous as vol  # type: ignore[import-untyped, unused-ignore]

from homeassistant import config_entries as ce
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN
from .helpers import handle_exception

CONF_LOCATION_IDX: Final = "location_idx"

SCAN_INTERVAL_DEFAULT: Final = timedelta(seconds=300)
SCAN_INTERVAL_MINIMUM: Final = timedelta(seconds=60)

_CONFIG_KEYS: Final = (CONF_USERNAME, CONF_PASSWORD, CONF_LOCATION_IDX)

_LOGGER = logging.getLogger(__name__)


class EvoConfigFlow(ce.ConfigFlow, domain=DOMAIN):
    """Handle an evohome config flow."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""

        _LOGGER.error(f"{self}: __init__()")  # noqa: G004

        self.options: dict[str, Any] = {}  # TO-DO: or: Mapping[str, Any]
        self.username: str | None = None
        self.password: str | None = None
        self.client: evo.EvohomeClient | None = None

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import a config_entry from configuration.yaml."""

        _LOGGER.warning(f"{self}: async_step_import({import_data})")  # noqa: G004

        data = {k: v for k, v in import_data.items() if k in _CONFIG_KEYS}
        options = {k: v for k, v in import_data.items() if k not in _CONFIG_KEYS}

        return self.async_create_entry(title=DOMAIN, data=data, options=options)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""

        _LOGGER.error(f"{self}: async_step_user({user_input})")  # noqa: G004

        return await self.async_step_user_credentials(user_input)

    async def async_step_user_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user credentials step."""

        _LOGGER.error(f"{self}: async_step_user_credentials({user_input})")  # noqa: G004

        errors = {}

        if user_input is not None:  # TO-DO: validate the user input
            partial_fnc = partial(
                evo.EvohomeClient,
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                # **tokens,
                session=async_get_clientsession(self.hass),
            )
            try:
                client = await self.hass.async_add_executor_job(partial_fnc)
            except evo.AuthenticationFailed as err:
                handle_exception(err)
                errors["base"] = "invalid_auth"
            else:
                # username/password valid so show user locations
                self.username = user_input[CONF_USERNAME]
                self.password = user_input[CONF_PASSWORD]
                self.client = client

                return await self.async_step_location_idx(user_input)

        return self.async_show_form(
            step_id="user_credentials",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): cv.string,
                    vol.Required(CONF_PASSWORD): cv.string,
                }
            ),
            errors=errors,
        )

    async def async_step_location_idx(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the location index step."""

        _LOGGER.warning(f"{self}: async_step_location_idx({user_input})")  # noqa: G004

        if user_input is not None:  # TO-DO: validate the user input
            return self.async_create_entry(title=DOMAIN, data=user_input)

        return self.async_show_form(
            step_id=CONF_LOCATION_IDX,
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_LOCATION_IDX, default=0): cv.positive_int,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""

        _LOGGER.warning("EvoConfigFlow: async_get_options_flow()")  # noqa: G004

        return EvoOptionsFlow(config_entry)


class EvoOptionsFlow(OptionsFlow):
    """Config flow options for Evohome."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize Evohome options flow."""

        _LOGGER.warning(f"{self}: __init__({config_entry})")  # noqa: G004

        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""

        _LOGGER.warning(f"{self}: async_step_init({user_input})")  # noqa: G004

        if user_input is not None:
            return self.async_create_entry(title=DOMAIN, data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, SCAN_INTERVAL_DEFAULT),
                    ): vol.All(cv.time_period, vol.Range(min=SCAN_INTERVAL_MINIMUM)),
                }
            ),
        )
