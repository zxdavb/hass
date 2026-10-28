"""Support for (EMEA/EU-based) Honeywell TCC systems.

Such systems provide heating/cooling and DHW and include Evohome, Round Thermostat, and
others.

Note that the API used by this integration's client does not support cooling.
"""

import logging
from typing import Any, Final

import evohomeasync as ec1
import evohomeasync2 as ec2
import probatio

from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_HIGH_PRECISION,
    CONF_LOCATION_IDX,
    DOMAIN,
    SCAN_INTERVAL_MINIMUM,
    YAML_BREAKS_IN_HA_VERSION,
)
from .coordinator import EvoConfigEntry, EvoDataUpdateCoordinator
from .services import async_setup_services
from .storage import TokenManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final = [Platform.BUTTON, Platform.CLIMATE, Platform.WATER_HEATER]

# location_idx & scan_interval are accepted, but ignored, so existing YAML can import
CONFIG_SCHEMA: Final = probatio.Schema(
    {
        DOMAIN: probatio.Schema(
            {
                probatio.Required(CONF_USERNAME): cv.string,
                probatio.Required(probatio.Secret(CONF_PASSWORD)): cv.string,
                probatio.Optional(CONF_LOCATION_IDX): cv.positive_int,
                probatio.Optional(CONF_SCAN_INTERVAL): probatio.All(
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

    async_setup_services(hass)

    if DOMAIN in config:
        hass.async_create_task(_async_import(hass, config[DOMAIN]))

    return True


async def _async_import(hass: HomeAssistant, conf: dict[str, Any]) -> None:
    """Import the YAML configuration and surface the appropriate repair issue."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={
            CONF_USERNAME: conf[CONF_USERNAME],
            CONF_PASSWORD: conf[CONF_PASSWORD],
        },
    )

    if result["type"] is FlowResultType.ABORT and result["reason"] not in (
        "already_configured",
        "single_instance_allowed",
    ):
        ir.async_create_issue(
            hass,
            DOMAIN,
            f"deprecated_yaml_import_issue_{result['reason']}",
            breaks_in_ha_version=YAML_BREAKS_IN_HA_VERSION,
            is_fixable=False,
            issue_domain=DOMAIN,
            severity=ir.IssueSeverity.WARNING,
            translation_key=f"deprecated_yaml_import_issue_{result['reason']}",
        )
        return

    ir.async_create_issue(
        hass,
        HOMEASSISTANT_DOMAIN,
        f"deprecated_yaml_{DOMAIN}",
        breaks_in_ha_version=YAML_BREAKS_IN_HA_VERSION,
        is_fixable=False,
        issue_domain=DOMAIN,
        severity=ir.IssueSeverity.WARNING,
        translation_key="deprecated_yaml",
        translation_placeholders={
            "domain": DOMAIN,
            "integration_title": "Honeywell Total Connect Comfort (Europe)",
        },
    )


async def async_setup_entry(hass: HomeAssistant, entry: EvoConfigEntry) -> None:
    """Set up Evohome from a config entry."""

    token_manager = TokenManager(
        hass,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        async_get_clientsession(hass),
    )
    coordinator = EvoDataUpdateCoordinator(
        hass,
        _LOGGER,
        entry,
        ec2.EvohomeClient(token_manager),
        client_v1=(
            ec1.EvohomeClient(token_manager)
            if entry.options.get(CONF_HIGH_PRECISION)
            else None
        ),
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def async_unload_entry(hass: HomeAssistant, entry: EvoConfigEntry) -> None:
    """Unload an Evohome config entry."""
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
