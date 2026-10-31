"""Support for (EMEA/EU-based) Honeywell TCC systems.

Such systems provide heating/cooling and DHW and include Evohome, Round Thermostat, and
others.

Note that the API used by this integration's client does not support cooling.
"""

import logging
from typing import Final

import evohomeasync as ec1
import evohomeasync2 as ec2
import probatio

from homeassistant.const import (
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_LOCATION_IDX,
    DOMAIN,
    EVOHOME_DATA,
    SCAN_INTERVAL_DEFAULT,
    SCAN_INTERVAL_MINIMUM,
)
from .coordinator import EvoAccountCoordinator, EvoDataUpdateCoordinator
from .services import async_setup_services
from .storage import TokenManager

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA: Final = probatio.Schema(
    {
        DOMAIN: probatio.Schema(
            {
                probatio.Required(CONF_USERNAME): cv.string,
                probatio.Required(probatio.Secret(CONF_PASSWORD)): cv.string,
                probatio.Optional(CONF_LOCATION_IDX, default=0): cv.positive_int,
                probatio.Optional(
                    CONF_SCAN_INTERVAL, default=SCAN_INTERVAL_DEFAULT
                ): probatio.All(
                    cv.time_period, probatio.Range(min=SCAN_INTERVAL_MINIMUM)
                ),
            }
        )
    },
    extra=probatio.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Evohome integration."""

    # Remove any (persistent) repair issues for deprecations that have been completed
    for issue_id in (
        "deprecated_clear_zone_override_service",
        "deprecated_preset_reset",
        "deprecated_reset_system_service",
        "deprecated_set_system_mode_service",
    ):
        ir.async_delete_issue(hass, DOMAIN, issue_id)

    token_manager = TokenManager(
        hass,
        config[DOMAIN][CONF_USERNAME],
        config[DOMAIN][CONF_PASSWORD],
        async_get_clientsession(hass),
    )
    account = EvoAccountCoordinator(
        hass,
        _LOGGER,
        ec2.EvohomeClient(token_manager),
        name=f"{DOMAIN}_account",
        client_v1=ec1.EvohomeClient(token_manager),
    )

    await account.async_register_shutdown()
    await account.async_first_refresh()

    if not account.last_update_success:
        _LOGGER.error(f"Failed to fetch initial data: {account.last_exception}")  # noqa: G004
        return False

    locations = account.client.locations
    location_idx: int = config[DOMAIN][CONF_LOCATION_IDX]

    if location_idx >= len(locations):
        _LOGGER.error(
            "Failed to fetch initial data: Config error: 'location_idx' = %s, "
            "but the valid range is 0-%s. Unable to continue. "
            "Fix any configuration errors and restart HA",
            location_idx,
            len(locations) - 1,
        )
        return False

    coordinator = EvoDataUpdateCoordinator(
        hass,
        _LOGGER,
        account,
        name=f"{DOMAIN}_coordinator",
        update_interval=config[DOMAIN][CONF_SCAN_INTERVAL],
        location_id=locations[location_idx].id,
    )

    await coordinator.async_register_shutdown()
    await coordinator.async_first_refresh()

    if not coordinator.last_update_success:
        _LOGGER.error(f"Failed to fetch initial data: {coordinator.last_exception}")  # noqa: G004
        return False

    hass.data[EVOHOME_DATA] = coordinator

    hass.async_create_task(
        async_load_platform(hass, Platform.CLIMATE, DOMAIN, {}, config)
    )
    hass.async_create_task(
        async_load_platform(hass, Platform.BUTTON, DOMAIN, {}, config)
    )
    hass.async_create_task(
        async_load_platform(hass, Platform.WATER_HEATER, DOMAIN, {}, config)
    )

    async_setup_services(hass)

    return True
