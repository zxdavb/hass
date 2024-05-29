"""The data update coordinator of the Evohome integration."""

from __future__ import annotations

from collections.abc import Awaitable
from datetime import timedelta
import logging
from typing import Any

import evohomeasync as ev1
from evohomeasync.schema import SZ_ID, SZ_SESSION_ID, SZ_TEMP
import evohomeasync2 as evo
from evohomeasync2.schema.const import (
    SZ_GATEWAY_ID,
    SZ_GATEWAY_INFO,
    SZ_LOCATION_ID,
    SZ_LOCATION_INFO,
    SZ_TIME_ZONE,
)

import homeassistant.config_entries as ce
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import homeassistant.util.dt as dt_util

from .const import (
    ACCESS_TOKEN,
    ACCESS_TOKEN_EXPIRES,
    CONF_LOCATION_IDX,
    DOMAIN,
    GWS,
    REFRESH_TOKEN,
    STORAGE_KEY,
    STORAGE_VER,
    TCS,
    USER_DATA,
    UTC_OFFSET,
)
from .helpers import dt_aware_to_naive, dt_local_to_aware, handle_exception

_LOGGER = logging.getLogger(__name__)


class EvoBroker:
    """Container for evohome client and data."""

    client: evo.EvohomeClient
    client_v1: ev1.EvohomeClient | None = None

    loc: evo.Location
    loc_utc_offset: timedelta

    tcs: evo.ControlSystem
    tcs_config: dict[str, Any]

    def __init__(self, hass: HomeAssistant, entry: ce.ConfigEntry) -> None:
        """Initialize the evohome broker and its data structures."""

        self.hass = hass
        self.entry = entry

        self.username: str = self.entry.data[CONF_USERNAME]
        self.loc_idx: int = self.entry.data[CONF_LOCATION_IDX]

        self._store: Store = Store(self.hass, STORAGE_VER, STORAGE_KEY)
        self._tokens: dict[str, Any] = {}
        self._session_id: str | None = None

        self.temps: dict[str, float | None] = {}

    async def login(self) -> None:
        """Start the evohome client and its data structure."""

        # if self.client is not None:  # TO-DO: should not be needed
        #     return

        await self.load_auth_tokens()

        self.client = evo.EvohomeClient(
            self.username,
            self.entry.data[CONF_PASSWORD],
            **self._tokens,
            session=async_get_clientsession(self.hass),
        )

        try:
            await self.client.login()  # may: raise evo.AuthenticationFailed
        except evo.AuthenticationFailed as err:
            handle_exception(err)
            raise

        try:
            _ = self.client.installation_info[self.loc_idx]
        except IndexError as err:
            msg = (
                f"Config error: '{CONF_LOCATION_IDX}' = {self.loc_idx}, "
                f"but the valid range is 0-{len(self.client.installation_info) - 1}. "
                "Unable to continue. Fix any configuration errors and restart HA"
            )
            raise evo.AuthenticationFailed(msg) from err

        await self.save_auth_tokens()

    async def start(self) -> None:
        """Start the evohome client and its data structure."""

        assert self.client is not None  # mypy check

        if _LOGGER.isEnabledFor(logging.DEBUG):
            loc_config = self.client.installation_info[self.loc_idx]

            loc_info = {
                SZ_LOCATION_ID: loc_config[SZ_LOCATION_INFO][SZ_LOCATION_ID],
                SZ_TIME_ZONE: loc_config[SZ_LOCATION_INFO][SZ_TIME_ZONE],
            }
            gwy_info = {
                SZ_GATEWAY_ID: loc_config[GWS][0][SZ_GATEWAY_INFO][SZ_GATEWAY_ID],
                TCS: loc_config[GWS][0][TCS],
            }
            _config = {
                SZ_LOCATION_INFO: loc_info,
                GWS: [{SZ_GATEWAY_INFO: gwy_info, TCS: loc_config[GWS][0][TCS]}],
            }
            _LOGGER.debug("Config = %s", _config)

        self.loc = self.client.locations[self.loc_idx]
        self.loc_utc_offset = timedelta(minutes=self.loc.timeZone[UTC_OFFSET])

        self.tcs = self.loc._gateways[0]._control_systems[0]  # noqa: SLF001
        self.tcs_config = self.client.installation_info[self.loc_idx][GWS][0][TCS][0]

        self.client_v1 = ev1.EvohomeClient(
            self.client.username,
            self.client.password,
            session_id=self._session_id,
            session=async_get_clientsession(self.hass),
        )

        await self.save_auth_tokens()

        await self.async_update()  # get initial state
        async_track_time_interval(
            self.hass, self.async_update, self.entry.options[CONF_SCAN_INTERVAL]
        )

    async def load_auth_tokens(self) -> None:
        """Load access tokens and session IDs from the store."""

        app_storage = dict(await self._store.async_load() or {})  # TO-DO: why dict()

        if app_storage.pop(CONF_USERNAME, None) != self.username:
            # any tokens won't be valid, and store might be corrupt
            # await self._store.async_save({})  # TO-DO: needed?
            self._tokens = {}
            self._session_id = None
            return

        # evohomeasync2 requires naive/local datetimes as strings
        if app_storage.get(ACCESS_TOKEN_EXPIRES) is not None and (
            expires := dt_util.parse_datetime(app_storage[ACCESS_TOKEN_EXPIRES])
        ):
            app_storage[ACCESS_TOKEN_EXPIRES] = dt_aware_to_naive(expires)

        user_data: dict[str, str] = app_storage.pop(USER_DATA, {})

        self._tokens = app_storage
        self._session_id = user_data.get(SZ_SESSION_ID)

    async def save_auth_tokens(self) -> None:
        """Save access tokens and session IDs to the store for later use."""

        # evohomeasync2 uses naive/local datetimes
        access_token_expires = dt_local_to_aware(
            self.client.access_token_expires  # type: ignore[arg-type]
        )

        app_storage: dict[str, Any] = {
            CONF_USERNAME: self.client.username,
            REFRESH_TOKEN: self.client.refresh_token,
            ACCESS_TOKEN: self.client.access_token,
            ACCESS_TOKEN_EXPIRES: access_token_expires.isoformat(),
        }

        if self.client_v1:
            app_storage[USER_DATA] = {
                SZ_SESSION_ID: self.client_v1.broker.session_id,
            }  # this is the schema for STORAGE_VER == 1
        else:
            app_storage[USER_DATA] = {}

        await self._store.async_save(app_storage)

    async def call_client_api(
        self,
        client_api: Awaitable[dict[str, Any] | None],
        update_state: bool = True,
    ) -> dict[str, Any] | None:
        """Call a client API and update the broker state if required."""

        try:
            result = await client_api
        except evo.RequestFailed as err:
            handle_exception(err)
            return None

        if update_state:  # wait a moment for system to quiesce before updating state
            async_call_later(self.hass, 1, self._update_v2_api_state)

        return result

    async def _update_v1_api_temps(self) -> None:
        """Get the latest high-precision temperatures of the default Location."""

        assert self.client_v1 is not None  # mypy check

        def get_session_id(client_v1: ev1.EvohomeClient) -> str | None:
            user_data = client_v1.user_data if client_v1 else None
            return user_data.get(SZ_SESSION_ID) if user_data else None  # type: ignore[return-value]

        session_id = get_session_id(self.client_v1)

        try:
            temps = await self.client_v1.get_temperatures()

        except ev1.InvalidSchema as err:
            _LOGGER.warning(
                (
                    "Unable to obtain high-precision temperatures. "
                    "It appears the JSON schema is not as expected, "
                    "so the high-precision feature will be disabled until next restart."
                    "Message is: %s"
                ),
                err,
            )
            self.client_v1 = None

        except ev1.RequestFailed as err:
            _LOGGER.warning(
                (
                    "Unable to obtain the latest high-precision temperatures. "
                    "Check your network and the vendor's service status page. "
                    "Proceeding without high-precision temperatures for now. "
                    "Message is: %s"
                ),
                err,
            )
            self.temps = {}  # high-precision temps now considered stale

        except Exception:
            self.temps = {}  # high-precision temps now considered stale
            raise

        else:
            if str(self.client_v1.location_id) != self.loc.locationId:
                _LOGGER.warning(
                    "The v2 API's configured location doesn't match "
                    "the v1 API's default location (there is more than one location), "
                    "so the high-precision feature will be disabled until next restart"
                )
                self.client_v1 = None
            else:
                self.temps = {str(i[SZ_ID]): i[SZ_TEMP] for i in temps}

        finally:
            if self.client_v1 and session_id != self.client_v1.broker.session_id:
                await self.save_auth_tokens()

        _LOGGER.debug("Temperatures = %s", self.temps)

    async def _update_v2_api_state(self, *args: Any) -> None:
        """Get the latest modes, temperatures, setpoints of a Location."""

        access_token = self.client.access_token  # maybe receive a new token?

        try:
            status = await self.loc.refresh_status()
        except evo.RequestFailed as err:
            handle_exception(err)
        else:
            async_dispatcher_send(self.hass, DOMAIN)
            _LOGGER.debug("Status = %s", status)
        finally:
            if access_token != self.client.access_token:
                await self.save_auth_tokens()

    async def async_update(self, *args: Any) -> None:
        """Get the latest state data of an entire Honeywell TCC Location.

        This includes state data for a Controller and all its child devices, such as the
        operating mode of the Controller and the current temp of its children (e.g.
        Zones, DHW controller).
        """
        await self._update_v2_api_state()

        if self.client_v1:
            await self._update_v1_api_temps()


class EvoCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the TCC API."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the coordinator."""
        super().__init__(*args, **kwargs)

        # without a listener, _schedule_refresh() won't be invoked by _async_refresh()
        self.async_add_listener(lambda: None)
