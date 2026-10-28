"""The tests for Evohome."""

from http import HTTPStatus
from typing import Any
from unittest.mock import Mock, patch

import aiohttp
from evohomeasync2 import exceptions as evo_exc
from freezegun.api import FrozenDateTimeFactory
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.evohome.const import CONF_HIGH_PRECISION, DOMAIN
from homeassistant.components.water_heater import (
    ATTR_CURRENT_TEMPERATURE,
    DOMAIN as WATER_HEATER_DOMAIN,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component

from .conftest import mock_evohome_api, mock_post_request, setup_evohome
from .const import USER_ID

from tests.common import MockConfigEntry

EXC_BAD_CONNECTION = aiohttp.ClientConnectionError(
    "Connection error",
)
EXC_BAD_CREDENTIALS = evo_exc.BadUserCredentialsError(
    "Authenticator response is invalid: {'error': 'invalid_grant'}",
    status=HTTPStatus.BAD_REQUEST,
)
EXC_TOO_MANY_REQUESTS = aiohttp.ClientResponseError(
    Mock(),
    (),
    status=HTTPStatus.TOO_MANY_REQUESTS,
    message=HTTPStatus.TOO_MANY_REQUESTS.phrase,
)
EXC_BAD_GATEWAY = aiohttp.ClientResponseError(
    Mock(), (), status=HTTPStatus.BAD_GATEWAY, message=HTTPStatus.BAD_GATEWAY.phrase
)


@pytest.fixture
def config_entry(config: dict[str, str]) -> MockConfigEntry:
    """Return an (unloaded) evohome config entry."""
    return MockConfigEntry(
        domain=DOMAIN, title=config[CONF_USERNAME], data=config, unique_id=USER_ID
    )


@pytest.mark.parametrize(
    ("exception", "expected_state"),
    [
        pytest.param(EXC_BAD_CONNECTION, ConfigEntryState.SETUP_RETRY, id="connection"),
        pytest.param(EXC_BAD_CREDENTIALS, ConfigEntryState.SETUP_ERROR, id="auth"),
        pytest.param(EXC_BAD_GATEWAY, ConfigEntryState.SETUP_RETRY, id="gateway"),
        pytest.param(EXC_TOO_MANY_REQUESTS, ConfigEntryState.SETUP_RETRY, id="429"),
    ],
)
async def test_authentication_failure_v2(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    exception: Exception,
    expected_state: ConfigEntryState,
) -> None:
    """Test failure to authenticate when setting up an evohome-compatible system."""

    config_entry.add_to_hass(hass)

    with patch(
        "_evohome.credentials.CredentialsManagerBase._request",
        side_effect=exception,
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)

    assert config_entry.state is expected_state


@pytest.mark.parametrize(
    "exception",
    [
        pytest.param(EXC_BAD_CONNECTION, id="connection"),
        pytest.param(EXC_BAD_GATEWAY, id="gateway"),
        pytest.param(EXC_TOO_MANY_REQUESTS, id="429"),
    ],
)
async def test_client_request_failure_v2(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    exception: Exception,
) -> None:
    """Test failure of a client request when setting up an evohome-compatible system."""

    config_entry.add_to_hass(hass)

    with (
        patch(
            "evohomeasync2.auth.CredentialsManagerBase._post_request",
            mock_post_request("default"),
        ),
        patch("_evohome.auth.AbstractAuth._request", side_effect=exception),
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.parametrize("install", ["default"])
@pytest.mark.usefixtures("evohome")
async def test_setup(hass: HomeAssistant, snapshot: SnapshotAssertion) -> None:
    """Test services after setup of evohome.

    Registered services vary by the type of system.
    """

    assert hass.services.async_services_for_domain(DOMAIN).keys() == snapshot


@pytest.mark.parametrize("install", ["default"])
@pytest.mark.usefixtures("evohome")
async def test_unload_entry(hass: HomeAssistant) -> None:
    """Test unloading the config entry."""

    entry = hass.config_entries.async_entries(DOMAIN)[0]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.parametrize("install", ["default"])
@pytest.mark.parametrize(
    ("options", "temperature"),
    [
        pytest.param({}, 23, id="default"),
        pytest.param({CONF_HIGH_PRECISION: False}, 23, id="disabled"),
        pytest.param({CONF_HIGH_PRECISION: True}, 23.0, id="enabled"),
    ],
)
async def test_high_precision_option(
    hass: HomeAssistant,
    dhw_id: str,
    temperature: float,
) -> None:
    """Test the high-precision option sets the precision of current temperatures."""

    state = hass.states.get(dhw_id)
    assert state is not None
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] == temperature
    assert type(state.attributes[ATTR_CURRENT_TEMPERATURE]) is type(temperature)


@pytest.mark.parametrize("install", ["multiple"])
@pytest.mark.usefixtures("evohome")
async def test_multiple_locations(hass: HomeAssistant) -> None:
    """Test that the systems of all locations are exposed."""

    assert {s.entity_id for s in hass.states.async_all(CLIMATE_DOMAIN)} >= {
        "climate.my_home",  # the controller of the 1st location
        "climate.kl",  # the controller of the 2nd location
    }
    assert len(hass.states.async_all(CLIMATE_DOMAIN)) == 2 + 8 + 5
    assert len(hass.states.async_all(WATER_HEATER_DOMAIN)) == 1


@pytest.mark.parametrize(
    "yaml_config",
    [
        pytest.param({}, id="minimal"),
        pytest.param(
            {"location_idx": 1, CONF_SCAN_INTERVAL: 600}, id="with_ignored_keys"
        ),
    ],
)
async def test_import_yaml(
    hass: HomeAssistant,
    config: dict[str, str],
    yaml_config: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Test the YAML configuration is imported as a config entry."""

    freezer.move_to("2024-07-10T12:00:00Z")

    with mock_evohome_api("default"):
        assert await async_setup_component(hass, DOMAIN, {DOMAIN: config | yaml_config})
        await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1

    entry = entries[0]
    assert entry.state is ConfigEntryState.LOADED
    assert entry.unique_id == USER_ID
    assert entry.data == config
    assert entry.options == {CONF_HIGH_PRECISION: True}

    assert issue_registry.async_get_issue(
        HOMEASSISTANT_DOMAIN, f"deprecated_yaml_{DOMAIN}"
    )


async def test_import_yaml_already_configured(
    hass: HomeAssistant,
    config: dict[str, str],
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Test the YAML configuration is not imported if already configured."""

    config_entry.add_to_hass(hass)

    with mock_evohome_api("default"):
        assert await async_setup_component(hass, DOMAIN, {DOMAIN: config})
        await hass.async_block_till_done()

    assert hass.config_entries.async_entries(DOMAIN) == [config_entry]
    assert config_entry.options == {}

    assert issue_registry.async_get_issue(
        HOMEASSISTANT_DOMAIN, f"deprecated_yaml_{DOMAIN}"
    )


@pytest.mark.parametrize(
    ("exception", "reason"),
    [
        pytest.param(EXC_BAD_CREDENTIALS, "invalid_auth", id="invalid_auth"),
        pytest.param(EXC_BAD_CONNECTION, "cannot_connect", id="cannot_connect"),
    ],
)
async def test_import_yaml_failure(
    hass: HomeAssistant,
    config: dict[str, str],
    exception: Exception,
    reason: str,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Test a repair issue is raised if the YAML configuration fails to import."""

    with patch(
        "_evohome.credentials.CredentialsManagerBase._request",
        side_effect=exception,
    ):
        assert await async_setup_component(hass, DOMAIN, {DOMAIN: config})
        await hass.async_block_till_done()

    assert hass.config_entries.async_entries(DOMAIN) == []

    assert issue_registry.async_get_issue(
        DOMAIN, f"deprecated_yaml_import_issue_{reason}"
    )
    assert not issue_registry.async_get_issue(
        HOMEASSISTANT_DOMAIN, f"deprecated_yaml_{DOMAIN}"
    )


_STALE_ISSUES = {  # issue_id: translation_key
    "deprecated_clear_zone_override_service": "deprecated_clear_zone_override_service",
    "deprecated_preset_reset": "deprecated_preset_reset",
    "deprecated_reset_system_service": "deprecated_reset_system_service",
    "deprecated_set_system_mode_service": "deprecated_controller_service",
}


@pytest.mark.parametrize("install", ["default"])
@pytest.mark.parametrize(
    "ignore_missing_translations",
    [
        [
            f"component.evohome.issues.{translation_key}.{key}"
            for translation_key in _STALE_ISSUES.values()
            for key in ("title", "description")
        ]
    ],
)
async def test_stale_deprecation_issues_removed(
    hass: HomeAssistant,
    config: dict[str, str],
    install: str,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Test persistent repair issues of completed deprecations are removed."""

    for issue_id, translation_key in _STALE_ISSUES.items():
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            is_persistent=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key=translation_key,
        )
        assert issue_registry.async_get_issue(DOMAIN, issue_id) is not None

    async for _ in setup_evohome(hass, config, install=install):
        pass

    for issue_id in _STALE_ISSUES:
        assert issue_registry.async_get_issue(DOMAIN, issue_id) is None
