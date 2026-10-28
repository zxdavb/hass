"""The constants of the Evohome integration."""

from datetime import timedelta
from enum import StrEnum, unique
from typing import Final

DOMAIN: Final = "evohome"

STORAGE_VER: Final = 1
STORAGE_KEY: Final = DOMAIN

CONF_HIGH_PRECISION: Final = "high_precision"

# Only used to validate the (deprecated) YAML configuration
CONF_LOCATION_IDX: Final = "location_idx"
SCAN_INTERVAL_MINIMUM: Final = timedelta(seconds=60)

UPDATE_INTERVAL: Final = timedelta(minutes=5)

YAML_BREAKS_IN_HA_VERSION: Final = "2027.5.0"

# Support for the refresh_system service is being deprecated
REFRESH_BREAKS_IN_HA_VERSION: Final = "2027.1.0"


@unique
class EvoService(StrEnum):
    """The Evohome services."""

    REFRESH_SYSTEM = "refresh_system"
    SET_SYSTEM_MODE = "set_system_mode"
    SET_ZONE_OVERRIDE = "set_zone_override"
    SET_DHW_OVERRIDE = "set_dhw_override"
