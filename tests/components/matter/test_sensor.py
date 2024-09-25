"""Test Matter sensors."""

from unittest.mock import MagicMock

from matter_server.client.models.node import MatterNode
import pytest
from syrupy import SnapshotAssertion

from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .common import (
    set_node_attribute,
    setup_integration_with_node_fixture,
    snapshot_matter_entities,
    trigger_subscription_callback,
)


@pytest.fixture(name="flow_sensor_node")
async def flow_sensor_node_fixture(
    hass: HomeAssistant, matter_client: MagicMock
) -> MatterNode:
    """Fixture for a flow sensor node."""
    return await setup_integration_with_node_fixture(hass, "flow_sensor", matter_client)


@pytest.fixture(name="humidity_sensor_node")
async def humidity_sensor_node_fixture(
    hass: HomeAssistant, matter_client: MagicMock
) -> MatterNode:
    """Fixture for a humidity sensor node."""
    return await setup_integration_with_node_fixture(
        hass, "humidity_sensor", matter_client
    )


@pytest.fixture(name="light_sensor_node")
async def light_sensor_node_fixture(
    hass: HomeAssistant, matter_client: MagicMock
) -> MatterNode:
    """Fixture for a light sensor node."""
    return await setup_integration_with_node_fixture(
        hass, "light_sensor", matter_client
    )


@pytest.fixture(name="pressure_sensor_node")
async def pressure_sensor_node_fixture(
    hass: HomeAssistant, matter_client: MagicMock
) -> MatterNode:
    """Fixture for a pressure sensor node."""
    return await setup_integration_with_node_fixture(
        hass, "pressure_sensor", matter_client
    )


@pytest.fixture(name="temperature_sensor_node")
async def temperature_sensor_node_fixture(
    hass: HomeAssistant, matter_client: MagicMock
) -> MatterNode:
    """Fixture for a temperature sensor node."""
    return await setup_integration_with_node_fixture(
        hass, "temperature_sensor", matter_client
    )


@pytest.fixture(name="eve_energy_plug_node")
async def eve_energy_plug_node_fixture(
    hass: HomeAssistant, matter_client: MagicMock
) -> MatterNode:
    """Fixture for a Eve Energy Plug node."""
    return await setup_integration_with_node_fixture(
        hass, "eve_energy_plug", matter_client
    )


@pytest.fixture(name="eve_thermo_node")
async def eve_thermo_node_fixture(
    hass: HomeAssistant, matter_client: MagicMock
) -> MatterNode:
    """Fixture for a Eve Thermo node."""
    return await setup_integration_with_node_fixture(hass, "eve_thermo", matter_client)


@pytest.fixture(name="eve_energy_plug_patched_node")
async def eve_energy_plug_patched_node_fixture(
    hass: HomeAssistant, matter_client: MagicMock
) -> MatterNode:
    """Fixture for a Eve Energy Plug node (patched to include Matter 1.3 energy clusters)."""
    return await setup_integration_with_node_fixture(
        hass, "eve_energy_plug_patched", matter_client
    )


@pytest.fixture(name="eve_weather_sensor_node")
async def eve_weather_sensor_node_fixture(
    hass: HomeAssistant, matter_client: MagicMock
) -> MatterNode:
    """Fixture for a Eve Weather sensor node."""
    return await setup_integration_with_node_fixture(
        hass, "eve_weather_sensor", matter_client
    )


@pytest.fixture(name="air_quality_sensor_node")
async def air_quality_sensor_node_fixture(
    hass: HomeAssistant, matter_client: MagicMock
) -> MatterNode:
    """Fixture for an air quality sensor (LightFi AQ1) node."""
    return await setup_integration_with_node_fixture(
        hass, "air_quality_sensor", matter_client
    )


@pytest.fixture(name="air_purifier_node")
async def air_purifier_node_fixture(
    hass: HomeAssistant, matter_client: MagicMock
) -> MatterNode:
    """Fixture for an air purifier node."""
    return await setup_integration_with_node_fixture(
        hass, "air_purifier", matter_client
    )


@pytest.fixture(name="dishwasher_node")
async def dishwasher_node_fixture(
    hass: HomeAssistant, matter_client: MagicMock
) -> MatterNode:
    """Fixture for an dishwasher node."""
    return await setup_integration_with_node_fixture(
        hass, "silabs_dishwasher", matter_client
    )


# This tests needs to be adjusted to remove lingering tasks
@pytest.mark.parametrize("expected_lingering_tasks", [True])
async def test_sensor_null_value(
    hass: HomeAssistant,
    matter_client: MagicMock,
    flow_sensor_node: MatterNode,
) -> None:
    """Test flow sensor."""
    state = hass.states.get("sensor.mock_flow_sensor_flow")
    assert state
    assert state.state == "0.0"

    set_node_attribute(flow_sensor_node, 1, 1028, 0, None)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get("sensor.mock_flow_sensor_flow")
    assert state
    assert state.state == "unknown"


# This tests needs to be adjusted to remove lingering tasks
@pytest.mark.parametrize("expected_lingering_tasks", [True])
async def test_flow_sensor(
    hass: HomeAssistant,
    matter_client: MagicMock,
    flow_sensor_node: MatterNode,
) -> None:
    """Test flow sensor."""
    state = hass.states.get("sensor.mock_flow_sensor_flow")
    assert state
    assert state.state == "0.0"

    set_node_attribute(flow_sensor_node, 1, 1028, 0, 20)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get("sensor.mock_flow_sensor_flow")
    assert state
    assert state.state == "2.0"


# This tests needs to be adjusted to remove lingering tasks
@pytest.mark.parametrize("expected_lingering_tasks", [True])
async def test_humidity_sensor(
    hass: HomeAssistant,
    matter_client: MagicMock,
    humidity_sensor_node: MatterNode,
) -> None:
    """Test humidity sensor."""
    state = hass.states.get("sensor.mock_humidity_sensor_humidity")
    assert state
    assert state.state == "0.0"

    set_node_attribute(humidity_sensor_node, 1, 1029, 0, 4000)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get("sensor.mock_humidity_sensor_humidity")
    assert state
    assert state.state == "40.0"


# This tests needs to be adjusted to remove lingering tasks
@pytest.mark.parametrize("expected_lingering_tasks", [True])
async def test_light_sensor(
    hass: HomeAssistant,
    matter_client: MagicMock,
    light_sensor_node: MatterNode,
) -> None:
    """Test light sensor."""
    state = hass.states.get("sensor.mock_light_sensor_illuminance")
    assert state
    assert state.state == "1.3"

    set_node_attribute(light_sensor_node, 1, 1024, 0, 3000)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get("sensor.mock_light_sensor_illuminance")
    assert state
    assert state.state == "2.0"


# This tests needs to be adjusted to remove lingering tasks
@pytest.mark.parametrize("expected_lingering_tasks", [True])
async def test_temperature_sensor(
    hass: HomeAssistant,
    matter_client: MagicMock,
    temperature_sensor_node: MatterNode,
) -> None:
    """Test temperature sensor."""
    state = hass.states.get("sensor.mock_temperature_sensor_temperature")
    assert state
    assert state.state == "21.0"

    set_node_attribute(temperature_sensor_node, 1, 1026, 0, 2500)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get("sensor.mock_temperature_sensor_temperature")
    assert state
    assert state.state == "25.0"


# This tests needs to be adjusted to remove lingering tasks
@pytest.mark.parametrize("expected_lingering_tasks", [True])
async def test_battery_sensor(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    matter_client: MagicMock,
    eve_contact_sensor_node: MatterNode,
) -> None:
    """Test battery sensor."""
    entity_id = "sensor.eve_door_battery"
    state = hass.states.get(entity_id)
    assert state
    assert state.state == "100"

    set_node_attribute(eve_contact_sensor_node, 1, 47, 12, 100)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get(entity_id)
    assert state
    assert state.state == "50"

    entry = entity_registry.async_get(entity_id)

    assert entry
    assert entry.entity_category == EntityCategory.DIAGNOSTIC


# This tests needs to be adjusted to remove lingering tasks
@pytest.mark.parametrize("expected_lingering_tasks", [True])
async def test_battery_sensor_voltage(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    matter_client: MagicMock,
    eve_contact_sensor_node: MatterNode,
) -> None:
    """Test battery voltage sensor."""
    entity_id = "sensor.eve_door_voltage"
    state = hass.states.get(entity_id)
    assert state
    assert state.state == "3.558"

    set_node_attribute(eve_contact_sensor_node, 1, 47, 11, 4234)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get(entity_id)
    assert state
    assert state.state == "4.234"

    entry = entity_registry.async_get(entity_id)

    assert entry
    assert entry.entity_category == EntityCategory.DIAGNOSTIC


# This tests needs to be adjusted to remove lingering tasks
@pytest.mark.parametrize("expected_lingering_tasks", [True])
async def test_eve_thermo_sensor(
    hass: HomeAssistant,
    matter_client: MagicMock,
    eve_thermo_node: MatterNode,
) -> None:
    """Test Eve Thermo."""
    # Valve position
    state = hass.states.get("sensor.eve_thermo_valve_position")
    assert state
    assert state.state == "10"

    set_node_attribute(eve_thermo_node, 1, 319486977, 319422488, 0)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get("sensor.eve_thermo_valve_position")
    assert state
    assert state.state == "0"


# This tests needs to be adjusted to remove lingering tasks
@pytest.mark.parametrize("expected_lingering_tasks", [True])
async def test_pressure_sensor(
    hass: HomeAssistant,
    matter_client: MagicMock,
    pressure_sensor_node: MatterNode,
) -> None:
    """Test pressure sensor."""
    state = hass.states.get("sensor.mock_pressure_sensor_pressure")
    assert state
    assert state.state == "0.0"

    set_node_attribute(pressure_sensor_node, 1, 1027, 0, 1010)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get("sensor.mock_pressure_sensor_pressure")
    assert state
    assert state.state == "101.0"


async def test_eve_weather_sensor_custom_cluster(
    hass: HomeAssistant,
    matter_client: MagicMock,
    eve_weather_sensor_node: MatterNode,
) -> None:
    """Test weather sensor created from (Eve) custom cluster."""
    # pressure sensor on Eve custom cluster
    state = hass.states.get("sensor.eve_weather_pressure")
    assert state
    assert state.state == "1008.5"

    set_node_attribute(eve_weather_sensor_node, 1, 319486977, 319422484, 800)
    await trigger_subscription_callback(hass, matter_client)
    state = hass.states.get("sensor.eve_weather_pressure")
    assert state
    assert state.state == "800.0"


# This tests needs to be adjusted to remove lingering tasks
@pytest.mark.parametrize("expected_lingering_tasks", [True])
async def test_air_quality_sensor(
    hass: HomeAssistant,
    matter_client: MagicMock,
    air_quality_sensor_node: MatterNode,
) -> None:
    """Test air quality sensor."""
    # Carbon Dioxide
    state = hass.states.get("sensor.lightfi_aq1_air_quality_sensor_carbon_dioxide")
    assert state
    assert state.state == "678.0"

    set_node_attribute(air_quality_sensor_node, 1, 1037, 0, 789)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get("sensor.lightfi_aq1_air_quality_sensor_carbon_dioxide")
    assert state
    assert state.state == "789.0"

    # PM1
    state = hass.states.get("sensor.lightfi_aq1_air_quality_sensor_pm1")
    assert state
    assert state.state == "3.0"

    set_node_attribute(air_quality_sensor_node, 1, 1068, 0, 50)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get("sensor.lightfi_aq1_air_quality_sensor_pm1")
    assert state
    assert state.state == "50.0"

    # PM2.5
    state = hass.states.get("sensor.lightfi_aq1_air_quality_sensor_pm2_5")
    assert state
    assert state.state == "3.0"

    set_node_attribute(air_quality_sensor_node, 1, 1066, 0, 50)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get("sensor.lightfi_aq1_air_quality_sensor_pm2_5")
    assert state
    assert state.state == "50.0"

    # PM10
    state = hass.states.get("sensor.lightfi_aq1_air_quality_sensor_pm10")
    assert state
    assert state.state == "3.0"

    set_node_attribute(air_quality_sensor_node, 1, 1069, 0, 50)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get("sensor.lightfi_aq1_air_quality_sensor_pm10")
    assert state
    assert state.state == "50.0"


async def test_operational_state_sensor(
    hass: HomeAssistant,
    matter_client: MagicMock,
    dishwasher_node: MatterNode,
) -> None:
    """Test dishwasher sensor."""
    # OperationalState Cluster / OperationalState attribute (1/96/4)
    state = hass.states.get("sensor.dishwasher_operational_state")
    assert state
    assert state.state == "stopped"
    assert state.attributes["options"] == [
        "stopped",
        "running",
        "paused",
        "error",
        "extra_state",
    ]

    set_node_attribute(dishwasher_node, 1, 96, 4, 8)
    await trigger_subscription_callback(hass, matter_client)

    state = hass.states.get("sensor.dishwasher_operational_state")
    assert state
    assert state.state == "extra_state"


# This tests needs to be adjusted to remove lingering tasks
@pytest.mark.parametrize("expected_lingering_tasks", [True])
async def test_sensors(
    hass: HomeAssistant,
    matter_client: MagicMock,
    matter_devices: MatterNode,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test sensors."""
    snapshot_matter_entities(hass, entity_registry, snapshot, Platform.SENSOR)
