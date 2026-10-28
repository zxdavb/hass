"""The tests for the config flow of Evohome."""

from http import HTTPStatus
from unittest.mock import patch

from evohomeasync2 import exceptions as evo_exc
import pytest

from homeassistant.components.evohome.const import CONF_HIGH_PRECISION, DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import mock_evohome_api
from .const import USER_ID

from tests.common import MockConfigEntry

EXC_BAD_CREDENTIALS = evo_exc.BadUserCredentialsError(
    "Authenticator response is invalid: {'error': 'invalid_grant'}",
    status=HTTPStatus.BAD_REQUEST,
)
EXC_BAD_GATEWAY = evo_exc.ApiCallFailedError(
    "502 Bad Gateway", status=HTTPStatus.BAD_GATEWAY
)


async def test_user_flow(hass: HomeAssistant, config: dict[str, str]) -> None:
    """Test the full user flow."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    with (
        mock_evohome_api("default"),
        patch("homeassistant.components.evohome.async_setup_entry"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], config
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == config[CONF_USERNAME]
    assert result["data"] == config
    assert result["options"] == {}
    assert result["result"].unique_id == USER_ID


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        pytest.param(EXC_BAD_CREDENTIALS, "invalid_auth", id="invalid_auth"),
        pytest.param(EXC_BAD_GATEWAY, "cannot_connect", id="cannot_connect"),
        pytest.param(ValueError, "unknown", id="unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    config: dict[str, str],
    exception: Exception,
    error: str,
) -> None:
    """Test the user flow recovers from errors."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "evohomeasync2.EvohomeClient.setup",
        side_effect=exception,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], config
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    with (
        mock_evohome_api("default"),
        patch("homeassistant.components.evohome.async_setup_entry"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], config
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_no_systems(
    hass: HomeAssistant, config: dict[str, str]
) -> None:
    """Test the user flow when the account has no heating systems."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with (
        mock_evohome_api("default"),
        patch(
            "tests.components.evohome.conftest.user_locations_config_fixture",
            return_value=[],
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], config
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_systems"}


async def test_user_flow_single_instance(
    hass: HomeAssistant, config: dict[str, str]
) -> None:
    """Test only one config entry is allowed."""

    MockConfigEntry(domain=DOMAIN, data=config, unique_id=USER_ID).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


@pytest.mark.parametrize("install", ["default"])
@pytest.mark.usefixtures("evohome")
async def test_options_flow(hass: HomeAssistant) -> None:
    """Test the options flow enables high-precision temperatures."""

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.runtime_data.client_v1 is None

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    with mock_evohome_api("default"):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_HIGH_PRECISION: True}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_HIGH_PRECISION: True}

    # the entry is reloaded, with the client for high-precision temperatures
    assert entry.runtime_data.client_v1 is not None
