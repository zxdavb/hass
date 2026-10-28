"""Support for (EMEA/EU-based) Honeywell TCC systems."""

from collections.abc import Awaitable
from http import HTTPStatus
import logging
from typing import override

import evohomeasync as ec1
import evohomeasync2 as ec2
from evohomeasync2.const import (
    SZ_DHW,
    SZ_GATEWAY_ID,
    SZ_GATEWAY_INFO,
    SZ_GATEWAYS,
    SZ_LOCATION_ID,
    SZ_LOCATION_INFO,
    SZ_TEMPERATURE_CONTROL_SYSTEMS,
    SZ_TIME_ZONE,
    SZ_USE_DAYLIGHT_SAVE_SWITCHING,
    SZ_ZONES,
)
from evohomeasync2.typedefs import EvoLocStatusT, EvoTcsConfigResponseT

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, UPDATE_INTERVAL

type EvoConfigEntry = ConfigEntry[EvoDataUpdateCoordinator]


class EvoDataUpdateCoordinator(DataUpdateCoordinator[dict[str, EvoLocStatusT]]):
    """Coordinator for evohome integration/client."""

    config_entry: EvoConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        config_entry: EvoConfigEntry,
        client_v2: ec2.EvohomeClient,
        *,
        client_v1: ec1.EvohomeClient | None = None,
    ) -> None:
        """Class to manage fetching data."""

        super().__init__(
            hass,
            logger,
            config_entry=config_entry,
            name=f"{DOMAIN}_coordinator",
            update_interval=UPDATE_INTERVAL,
        )

        self.client = client_v2
        self.client_v1 = client_v1

        # the locations with a TCS (will be populated by _async_setup())
        self.locations: list[ec2.Location] = []
        self.temps: dict[str, float | None] = {}

        self._first_refresh_done = False  # get schedules only after first refresh

    @property
    def systems(self) -> list[ec2.ControlSystem]:
        """Return the TCS of each location (each location has at most one TCS)."""
        return [loc.tcs for loc in self.locations if loc.tcs is not None]

    @override
    async def _async_setup(self) -> None:
        """Set up the coordinator.

        Fetch the user information, and the configuration of their locations.
        """

        try:
            await self.client.setup()  # only config for now
        except ec2.BadUserCredentialsError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="invalid_auth",
            ) from err
        except ec2.EvohomeError as err:
            raise UpdateFailed(err) from err

        self.locations = [loc for loc in self.client.locations if loc.tcs is not None]

        if self.logger.isEnabledFor(logging.DEBUG):
            for loc in self.locations:
                self._log_location_config(loc)

    def _log_location_config(self, loc: ec2.Location) -> None:
        """Log the configuration of a location (for debugging)."""

        tcs = loc.tcs
        assert tcs is not None  # mypy

        loc_info = {
            SZ_LOCATION_ID: loc.id,
            SZ_TIME_ZONE: loc.config[SZ_TIME_ZONE],
            SZ_USE_DAYLIGHT_SAVE_SWITCHING: loc.config[SZ_USE_DAYLIGHT_SAVE_SWITCHING],
        }
        tcs_info: EvoTcsConfigResponseT = {
            **tcs.config,
            SZ_ZONES: [zone.config for zone in tcs.zones],
        }
        if tcs.hotwater:
            tcs_info[SZ_DHW] = tcs.hotwater.config
        gwy_info = {
            SZ_GATEWAY_ID: tcs.gateway.id,
            SZ_TEMPERATURE_CONTROL_SYSTEMS: [tcs_info],
        }
        config = {
            SZ_LOCATION_INFO: loc_info,
            SZ_GATEWAYS: [{SZ_GATEWAY_INFO: gwy_info}],
        }
        self.logger.debug("Config = %s", [config])

    async def call_client_api[_T](
        self,
        client_api: Awaitable[_T],
        request_refresh: bool = True,
    ) -> _T | None:
        """Call a client API and update the Coordinator state if required."""

        try:
            result = await client_api

        except ec2.AuthenticationFailedError:
            raise

        except ec2.ApiCallFailedError as err:
            self.logger.error(err)
            return None

        if request_refresh:  # wait a moment for system to quiesce before updating state
            await self.async_request_refresh()  # hass.async_create_task() won't help

        return result

    async def _update_v1_api_temps(self) -> None:
        """Get the latest high-precision temperatures of all the Locations."""

        assert self.client_v1 is not None  # mypy check

        try:
            await self.client_v1.get_status()

        except ec1.BadUserCredentialsError as err:
            self.logger.warning(
                (
                    "Unable to obtain high-precision temperatures. "
                    "The feature will be disabled until next restart: %r"
                ),
                err,
            )
            self.client_v1 = None

        except ec1.EvohomeError as err:
            self.logger.warning(
                (
                    "Unable to obtain the latest high-precision temperatures. "
                    "They will be ignored this refresh cycle: %r"
                ),
                err,
            )
            self.temps = {}  # high-precision temps now considered stale

        else:
            self.temps = {}
            for loc in self.locations:
                if (loc_v1 := self.client_v1.location_by_id.get(loc.id)) is None:
                    continue
                self.temps |= await loc_v1.get_temperatures(dont_update_status=True)

        self.logger.debug("Status (high-res temps) = %s", self.temps)

    async def _update_v2_api_state(self, loc: ec2.Location) -> None:
        """Get the latest modes, temperatures, setpoints of a Location."""

        try:
            status = await loc.get_status()

        except ec2.ApiCallFailedError as err:
            if err.status != HTTPStatus.TOO_MANY_REQUESTS:
                raise UpdateFailed(err) from err

            raise UpdateFailed("The vendor's API rate limit has been exceeded") from err

        except ec2.EvohomeError as err:
            raise UpdateFailed(err) from err

        self.logger.debug("Status = %s", status)

    async def _update_v2_schedules(self, tcs: ec2.ControlSystem) -> None:
        for zone in tcs.zones:
            try:
                await zone.get_schedule()
            except ec2.InvalidScheduleError as err:
                self.logger.warning(
                    "Zone '%s' has an invalid/missing schedule: %r", zone.name, err
                )

        if dhw := tcs.hotwater:
            try:
                await dhw.get_schedule()
            except ec2.InvalidScheduleError as err:
                self.logger.warning("DHW has an invalid/missing schedule: %r", err)

    @override
    async def _async_update_data(self) -> dict[str, EvoLocStatusT]:
        """Fetch the latest state of all the TCC Locations.

        This includes state data for each Controller and all its child devices, such as
        the operating mode of the Controller and the current temp of its children (e.g.
        Zones, DHW controller).
        """

        for loc in self.locations:
            await self._update_v2_api_state(loc)  # may raise UpdateFailed
        if self.client_v1:
            await self._update_v1_api_temps()  # will never raise UpdateFailed

        # to speed up HA startup, don't update entity schedules during initial
        # async_config_entry_first_refresh(), only during subsequent async_refresh()...
        if self._first_refresh_done:
            for tcs in self.systems:
                await self._update_v2_schedules(tcs)
        else:
            self._first_refresh_done = True

        return {loc.id: loc.status for loc in self.locations}
