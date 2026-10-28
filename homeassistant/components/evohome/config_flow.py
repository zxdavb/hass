"""Config flow for the Evohome integration."""

import logging
from typing import Any, Final, override

import evohomeasync2 as ec2
from evohomeasync2.const import SZ_USER_ID
import probatio

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import CONF_HIGH_PRECISION, DOMAIN
from .storage import TokenManager

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA: Final = probatio.Schema(
    {
        probatio.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        probatio.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(
                type=TextSelectorType.PASSWORD, autocomplete="current-password"
            )
        ),
    }
)


class NoSystemsError(Exception):
    """Error to indicate the account has no locations with a TCS."""


async def _validate_credentials(hass: HomeAssistant, data: dict[str, Any]) -> str:
    """Validate the user credentials and return the account's user id."""

    token_manager = TokenManager(
        hass,
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        async_get_clientsession(hass),
    )
    client = ec2.EvohomeClient(token_manager)

    await client.setup()

    if not any(loc.tcs for loc in client.locations):
        raise NoSystemsError

    return client.user_account[SZ_USER_ID]


class EvohomeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Evohome."""

    VERSION = 1

    async def _async_validate(self, data: dict[str, Any]) -> str | None:
        """Validate the credentials and set the unique id; return any error."""

        try:
            user_id = await _validate_credentials(self.hass, data)
        except ec2.BadUserCredentialsError:
            return "invalid_auth"
        except ec2.ApiCallFailedError:
            return "cannot_connect"
        except NoSystemsError:
            return "no_systems"
        except Exception:
            _LOGGER.exception("Unexpected exception")
            return "unknown"

        await self.async_set_unique_id(user_id)
        self._abort_if_unique_id_configured()
        return None

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if (error := await self._async_validate(user_input)) is None:
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME], data=user_input
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import the Evohome config from configuration.yaml."""

        if (error := await self._async_validate(import_data)) is not None:
            return self.async_abort(reason=error)

        # high-precision temps were always enabled for YAML-based configs
        return self.async_create_entry(
            title=import_data[CONF_USERNAME],
            data=import_data,
            options={CONF_HIGH_PRECISION: True},
        )

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: ConfigEntry) -> EvohomeOptionsFlow:
        """Get the options flow for this handler."""
        return EvohomeOptionsFlow()


class EvohomeOptionsFlow(OptionsFlowWithReload):
    """Handle the options flow for Evohome."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""

        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        CONF_HIGH_PRECISION,
                        default=self.config_entry.options.get(
                            CONF_HIGH_PRECISION, False
                        ),
                    ): bool,
                }
            ),
        )
