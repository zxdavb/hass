"""The tests for the button platform of evohome.

All evohome systems have a controller and at least one zone.
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock, patch

from evohomeasync2 import ControlSystem, EvohomeClient, HotWater, Zone
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant

from .const import TEST_INSTALLS


@pytest.fixture
def system_button_id(
    evohome: MagicMock, entity_id: Callable[[Platform, str], str]
) -> str:
    """Return the entity_id of the system reset button."""

    evo: EvohomeClient = evohome.return_value
    tcs: ControlSystem = evo.tcs

    return entity_id(Platform.BUTTON, f"{tcs.id}_reset")


@pytest.fixture
def dhw_button_id(evohome: MagicMock, entity_id: Callable[[Platform, str], str]) -> str:
    """Return the entity_id of the DHW reset button."""

    evo: EvohomeClient = evohome.return_value
    dhw: HotWater | None = evo.tcs.hotwater

    assert dhw is not None, "Fixture has no DHW zone"

    return entity_id(Platform.BUTTON, f"{dhw.id}_reset")


@pytest.fixture
def zone_button_id(
    evohome: MagicMock, entity_id: Callable[[Platform, str], str]
) -> str:
    """Return the entity_id of the first zone's reset button."""

    evo: EvohomeClient = evohome.return_value
    tcs: ControlSystem = evo.tcs

    zone: Zone = evo.tcs.zones[0]

    return entity_id(
        Platform.BUTTON,
        f"{zone.id}z_reset" if zone.id == tcs.id else f"{zone.id}_reset",
    )


@pytest.mark.parametrize("install", [*TEST_INSTALLS, "botched"])
@pytest.mark.usefixtures("evohome")
async def test_setup_platform(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
) -> None:
    """Test that button entities are created after setup of evohome."""

    button_states = hass.states.async_all(BUTTON_DOMAIN)
    assert button_states

    for x in button_states:
        assert x == snapshot(name=f"{x.entity_id}-state")


@pytest.mark.parametrize("install", ["default"])
@pytest.mark.usefixtures("evohome")
async def test_system_reset_button_press(
    hass: HomeAssistant,
    system_button_id: str,
) -> None:
    """Test SERVICE_PRESS on the system reset button."""

    with patch("evohomeasync2.control_system.ControlSystem.reset") as mock_fcn:
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {ATTR_ENTITY_ID: system_button_id},
            blocking=True,
        )

        mock_fcn.assert_awaited_once_with()


@pytest.mark.parametrize("install", ["default"])
@pytest.mark.usefixtures("evohome")
async def test_zone_reset_button_press(
    hass: HomeAssistant,
    zone_button_id: str,
) -> None:
    """Test SERVICE_PRESS on a zone reset button."""

    with patch("evohomeasync2.zone.Zone.reset") as mock_fcn:
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {ATTR_ENTITY_ID: zone_button_id},
            blocking=True,
        )

        mock_fcn.assert_awaited_once_with()


@pytest.mark.parametrize("install", ["default"])
@pytest.mark.usefixtures("evohome")
async def test_dhw_reset_button_press(
    hass: HomeAssistant,
    dhw_button_id: str,
) -> None:
    """Test SERVICE_PRESS on the DHW reset button."""

    with patch("evohomeasync2.hotwater.HotWater.reset") as mock_fcn:
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {ATTR_ENTITY_ID: dhw_button_id},
            blocking=True,
        )

        mock_fcn.assert_awaited_once_with()


@pytest.mark.parametrize("install", ["default"])
@pytest.mark.usefixtures("evohome")
async def test_extra_state_attrs_faults_not_deprecated(
    hass: HomeAssistant,
    system_button_id: str,
) -> None:
    """Test that Button entities don't expose activeFaults in their state attributes.

    EvoResetButtonBase inherits EvoEntity.extra_state_attributes but has
    _evo_state_attr_names = (), so _handle_coordinator_update never puts
    "activeFaults" into _device_state_attrs.  The deprecation guard in
    extra_state_attributes therefore never fires for button entities.
    """
    state = hass.states.get(system_button_id)
    assert state is not None
    assert "activeFaults" not in state.attributes.get("status", {})
