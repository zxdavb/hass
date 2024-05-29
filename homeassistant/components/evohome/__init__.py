"""Support for (EMEA/EU-based) Honeywell TCC systems.

Such systems provide heating/cooling and DHW and include Evohome, Round Thermostat, and
others.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

import evohomeasync2 as evo
from evohomeasync2.schema.const import (
    SZ_ALLOWED_SYSTEM_MODES,
    SZ_AUTO_WITH_RESET,
    SZ_CAN_BE_TEMPORARY,
    SZ_HEAT_SETPOINT,
    SZ_SETPOINT_STATUS,
    SZ_STATE_STATUS,
    SZ_SYSTEM_MODE,
    SZ_SYSTEM_MODE_STATUS,
    SZ_TIME_UNTIL,
    SZ_TIMING_MODE,
    SZ_UNTIL,
)
import voluptuous as vol

import homeassistant.config_entries as ce
from homeassistant.const import ATTR_ENTITY_ID, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.service import verify_domain_control
from homeassistant.helpers.typing import ConfigType
import homeassistant.util.dt as dt_util

from .const import (
    ATTR_DURATION_DAYS,
    ATTR_DURATION_HOURS,
    ATTR_SYSTEM_MODE,
    CONFIG_SCHEMA,
    DOMAIN,
    RESET_ZONE_OVERRIDE_SCHEMA,
    SET_ZONE_OVERRIDE_SCHEMA,
    EvoService,
)
from .coordinator import EvoBroker, EvoCoordinator
from .helpers import convert_dict, convert_until

__all__ = ["CONFIG_SCHEMA", "DOMAIN", "EvoChild", "EvoDevice", "async_setup"]


_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Import an evohome integration into config flow."""

    _LOGGER.warning("Async_setup(%s, %s)", hass, config)

    hass.data[DOMAIN] = {}  # why? (BTW: hass.data[DOMAIN] raises KeyError)

    if DOMAIN in config and not hass.config_entries.async_entries(DOMAIN):
        # perform a one-off import from the configuration.yaml file
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": ce.SOURCE_IMPORT},
                data=config[DOMAIN],
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ce.ConfigEntry) -> bool:
    """Create a (EMEA/EU-based) Honeywell TCC system."""

    _LOGGER.error("Async_setup_entry(%s, %s)", hass, entry)

    broker = EvoBroker(hass, entry)
    hass.data[DOMAIN] = {"broker": broker}

    try:
        await broker.login()  # login, and get initial state
    except evo.AuthenticationFailed:
        return False

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN]["broker"] = broker = EvoBroker(hass, entry)

    hass.data[DOMAIN]["coordinator"] = coordinator = EvoCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_coordinator",
        update_interval=entry.options[CONF_SCAN_INTERVAL],
        update_method=broker.async_update,
    )
    await coordinator.async_refresh()  # get initial state

    hass.async_create_task(async_load_platform(hass, Platform.CLIMATE, DOMAIN, {}, {}))
    if broker.tcs.hotwater:
        hass.async_create_task(
            async_load_platform(hass, Platform.WATER_HEATER, DOMAIN, {}, {})
        )

    _setup_service_functions(hass, broker)

    return True


# async def async_update_listener(hass: HomeAssistant, entry: ce.ConfigEntry) -> None:
# """Handle options update."""
# hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))


# async def async_unload_entry(hass: HomeAssistant, entry: ce.ConfigEntry) -> bool:
# """Unload a config entry."""
# broker: RamsesBroker = hass.data[DOMAIN][entry.entry_id]
# if not await broker.async_unload_platforms():
#     return False
# for svc in hass.services.async_services_for_domain(DOMAIN):
#     hass.services.async_remove(DOMAIN, svc)
# hass.data[DOMAIN].pop(entry.entry_id)
#
# return True


@callback
def _setup_service_functions(hass: HomeAssistant, broker: EvoBroker) -> None:
    """Set up the service handlers for the system/zone operating modes.

    Not all Honeywell TCC-compatible systems support all operating modes. In addition,
    each mode will require any of four distinct service schemas. This has to be
    enumerated before registering the appropriate handlers.

    It appears that all TCC-compatible systems support the same three zones modes.
    """

    @verify_domain_control(hass, DOMAIN)
    async def force_refresh(call: ServiceCall) -> None:
        """Obtain the latest state data via the vendor's RESTful API."""
        await broker.async_update()

    @verify_domain_control(hass, DOMAIN)
    async def set_system_mode(call: ServiceCall) -> None:
        """Set the system mode."""
        payload = {
            "unique_id": broker.tcs.systemId,
            "service": call.service,
            "data": call.data,
        }
        async_dispatcher_send(hass, DOMAIN, payload)

    @verify_domain_control(hass, DOMAIN)
    async def set_zone_override(call: ServiceCall) -> None:
        """Set the zone override (setpoint)."""
        entity_id = call.data[ATTR_ENTITY_ID]

        registry = er.async_get(hass)
        registry_entry = registry.async_get(entity_id)

        if registry_entry is None or registry_entry.platform != DOMAIN:
            raise ValueError(f"'{entity_id}' is not a known {DOMAIN} entity")

        if registry_entry.domain != "climate":
            raise ValueError(f"'{entity_id}' is not an {DOMAIN} controller/zone")

        payload = {
            "unique_id": registry_entry.unique_id,
            "service": call.service,
            "data": call.data,
        }

        async_dispatcher_send(hass, DOMAIN, payload)

    hass.services.async_register(DOMAIN, EvoService.REFRESH_SYSTEM, force_refresh)

    # Enumerate which operating modes are supported by this system
    modes = broker.tcs_config[SZ_ALLOWED_SYSTEM_MODES]

    # Not all systems support "AutoWithReset": register this handler only if required
    if [m[SZ_SYSTEM_MODE] for m in modes if m[SZ_SYSTEM_MODE] == SZ_AUTO_WITH_RESET]:
        hass.services.async_register(DOMAIN, EvoService.RESET_SYSTEM, set_system_mode)

    system_mode_schemas = []
    modes = [m for m in modes if m[SZ_SYSTEM_MODE] != SZ_AUTO_WITH_RESET]

    # Permanent-only modes will use this schema
    perm_modes = [m[SZ_SYSTEM_MODE] for m in modes if not m[SZ_CAN_BE_TEMPORARY]]
    if perm_modes:  # any of: "Auto", "HeatingOff": permanent only
        schema = vol.Schema({vol.Required(ATTR_SYSTEM_MODE): vol.In(perm_modes)})
        system_mode_schemas.append(schema)

    modes = [m for m in modes if m[SZ_CAN_BE_TEMPORARY]]

    # These modes are set for a number of hours (or indefinitely): use this schema
    temp_modes = [m[SZ_SYSTEM_MODE] for m in modes if m[SZ_TIMING_MODE] == "Duration"]
    if temp_modes:  # any of: "AutoWithEco", permanent or for 0-24 hours
        schema = vol.Schema(
            {
                vol.Required(ATTR_SYSTEM_MODE): vol.In(temp_modes),
                vol.Optional(ATTR_DURATION_HOURS): vol.All(
                    cv.time_period,
                    vol.Range(min=timedelta(hours=0), max=timedelta(hours=24)),
                ),
            }
        )
        system_mode_schemas.append(schema)

    # These modes are set for a number of days (or indefinitely): use this schema
    temp_modes = [m[SZ_SYSTEM_MODE] for m in modes if m[SZ_TIMING_MODE] == "Period"]
    if temp_modes:  # any of: "Away", "Custom", "DayOff", permanent or for 1-99 days
        schema = vol.Schema(
            {
                vol.Required(ATTR_SYSTEM_MODE): vol.In(temp_modes),
                vol.Optional(ATTR_DURATION_DAYS): vol.All(
                    cv.time_period,
                    vol.Range(min=timedelta(days=1), max=timedelta(days=99)),
                ),
            }
        )
        system_mode_schemas.append(schema)

    if system_mode_schemas:
        hass.services.async_register(
            DOMAIN,
            EvoService.SET_SYSTEM_MODE,
            set_system_mode,
            schema=vol.Schema(vol.Any(*system_mode_schemas)),
        )

    # The zone modes are consistent across all systems and use the same schema
    hass.services.async_register(
        DOMAIN,
        EvoService.RESET_ZONE_OVERRIDE,
        set_zone_override,
        schema=RESET_ZONE_OVERRIDE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        EvoService.SET_ZONE_OVERRIDE,
        set_zone_override,
        schema=SET_ZONE_OVERRIDE_SCHEMA,
    )


class EvoDevice(Entity):
    """Base for any evohome device.

    This includes the Controller, (up to 12) Heating Zones and (optionally) a
    DHW controller.
    """

    _attr_should_poll = False

    def __init__(
        self,
        evo_broker: EvoBroker,
        evo_device: evo.ControlSystem | evo.HotWater | evo.Zone,
    ) -> None:
        """Initialize the evohome entity."""
        self._evo_device = evo_device
        self._evo_broker = evo_broker
        self._evo_tcs = evo_broker.tcs

        self._device_state_attrs: dict[str, Any] = {}

    async def async_refresh(self, payload: dict | None = None) -> None:
        """Process any signals."""
        if payload is None:
            self.async_schedule_update_ha_state(force_refresh=True)
            return
        if payload["unique_id"] != self._attr_unique_id:
            return
        if payload["service"] in (
            EvoService.SET_ZONE_OVERRIDE,
            EvoService.RESET_ZONE_OVERRIDE,
        ):
            await self.async_zone_svc_request(payload["service"], payload["data"])
            return
        await self.async_tcs_svc_request(payload["service"], payload["data"])

    async def async_tcs_svc_request(self, service: str, data: dict[str, Any]) -> None:
        """Process a service request (system mode) for a controller."""
        raise NotImplementedError

    async def async_zone_svc_request(self, service: str, data: dict[str, Any]) -> None:
        """Process a service request (setpoint override) for a zone."""
        raise NotImplementedError

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the evohome-specific state attributes."""
        status = self._device_state_attrs
        if SZ_SYSTEM_MODE_STATUS in status:
            convert_until(status[SZ_SYSTEM_MODE_STATUS], SZ_TIME_UNTIL)
        if SZ_SETPOINT_STATUS in status:
            convert_until(status[SZ_SETPOINT_STATUS], SZ_UNTIL)
        if SZ_STATE_STATUS in status:
            convert_until(status[SZ_STATE_STATUS], SZ_UNTIL)

        return {"status": convert_dict(status)}

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        async_dispatcher_connect(self.hass, DOMAIN, self.async_refresh)


class EvoChild(EvoDevice):
    """Base for any evohome child.

    This includes (up to 12) Heating Zones and (optionally) a DHW controller.
    """

    _evo_id: str  # mypy hint

    def __init__(
        self, evo_broker: EvoBroker, evo_device: evo.HotWater | evo.Zone
    ) -> None:
        """Initialize a evohome Controller (hub)."""
        super().__init__(evo_broker, evo_device)

        self._schedule: dict[str, Any] = {}
        self._setpoints: dict[str, Any] = {}

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature of a Zone."""

        assert isinstance(self._evo_device, evo.HotWater | evo.Zone)  # mypy check

        if (temp := self._evo_broker.temps.get(self._evo_id)) is not None:
            # use high-precision temps if available
            return temp
        return self._evo_device.temperature

    @property
    def setpoints(self) -> dict[str, Any]:
        """Return the current/next setpoints from the schedule.

        Only Zones & DHW controllers (but not the TCS) can have schedules.
        """

        def _dt_evo_to_aware(dt_naive: datetime, utc_offset: timedelta) -> datetime:
            dt_aware = dt_naive.replace(tzinfo=dt_util.UTC) - utc_offset
            return dt_util.as_local(dt_aware)

        if not (schedule := self._schedule.get("DailySchedules")):
            return {}  # no scheduled setpoints when {'DailySchedules': []}

        day_time = dt_util.now()
        day_of_week = day_time.weekday()  # for evohome, 0 is Monday
        time_of_day = day_time.strftime("%H:%M:%S")

        try:
            # Iterate today's switchpoints until past the current time of day...
            day = schedule[day_of_week]
            sp_idx = -1  # last switchpoint of the day before
            for i, tmp in enumerate(day["Switchpoints"]):
                if time_of_day > tmp["TimeOfDay"]:
                    sp_idx = i  # current setpoint
                else:
                    break

            # Did the current SP start yesterday? Does the next start SP tomorrow?
            this_sp_day = -1 if sp_idx == -1 else 0
            next_sp_day = 1 if sp_idx + 1 == len(day["Switchpoints"]) else 0

            for key, offset, idx in (
                ("this", this_sp_day, sp_idx),
                ("next", next_sp_day, (sp_idx + 1) * (1 - next_sp_day)),
            ):
                sp_date = (day_time + timedelta(days=offset)).strftime("%Y-%m-%d")
                day = schedule[(day_of_week + offset) % 7]
                switchpoint = day["Switchpoints"][idx]

                switchpoint_time_of_day = dt_util.parse_datetime(
                    f"{sp_date}T{switchpoint['TimeOfDay']}"
                )
                assert switchpoint_time_of_day is not None  # mypy check
                dt_aware = _dt_evo_to_aware(
                    switchpoint_time_of_day, self._evo_broker.loc_utc_offset
                )

                self._setpoints[f"{key}_sp_from"] = dt_aware.isoformat()
                try:
                    self._setpoints[f"{key}_sp_temp"] = switchpoint[SZ_HEAT_SETPOINT]
                except KeyError:
                    self._setpoints[f"{key}_sp_state"] = switchpoint["DhwState"]

        except IndexError:
            self._setpoints = {}
            _LOGGER.warning(
                "Failed to get setpoints, report as an issue if this error persists",
                exc_info=True,
            )

        return self._setpoints

    async def _update_schedule(self) -> None:
        """Get the latest schedule, if any."""

        assert isinstance(self._evo_device, evo.HotWater | evo.Zone)  # mypy check

        try:
            self._schedule = await self._evo_broker.call_client_api(  # type: ignore[assignment]
                self._evo_device.get_schedule(), update_state=False
            )
        except evo.InvalidSchedule as err:
            _LOGGER.warning(
                "%s: Unable to retrieve the schedule: %s",
                self._evo_device,
                err,
            )
            self._schedule = {}

        _LOGGER.debug("Schedule['%s'] = %s", self.name, self._schedule)

    async def async_update(self) -> None:
        """Get the latest state data."""
        next_sp_from = self._setpoints.get("next_sp_from", "2000-01-01T00:00:00+00:00")
        next_sp_from_dt = dt_util.parse_datetime(next_sp_from)
        if next_sp_from_dt is None or dt_util.now() >= next_sp_from_dt:
            await self._update_schedule()  # no schedule, or it's out-of-date

        self._device_state_attrs = {"setpoints": self.setpoints}
