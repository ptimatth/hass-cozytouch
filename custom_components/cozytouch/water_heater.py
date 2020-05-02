"""Climate sensors for Cozytouch."""
import logging

import voluptuous as vol
from cozytouchpy.constant import DeviceState, DeviceType

import homeassistant.helpers.config_validation as cv
from homeassistant.components.water_heater import (
    ATTR_TEMPERATURE,
    STATE_ECO,
    STATE_ON,
    SUPPORT_AWAY_MODE,
    SUPPORT_OPERATION_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    WaterHeaterDevice,
)
from homeassistant.const import ATTR_ENTITY_ID, TEMP_CELSIUS

from . import async_make_request
from .const import (
    ATTR_TIME_PERIOD,
    COZYTOUCH_DATAS,
    DOMAIN,
    SERVICE_SET_AWAY_MODE,
    SERVICE_SET_BOOST_MODE,
    STATE_AUTO,
    STATE_MANUEL,
)

DEFAULT_MIN_TEMP = 50
DEFAULT_MAX_TEMP = 62

_LOGGER = logging.getLogger(__name__)

COZY_TO_HASS_STATE = {
    "manualEcoActive": STATE_ECO,
    "manualEcoInactive": STATE_MANUEL,
    "autoMode": STATE_AUTO,
}
HASS_TO_COZY_STATE = {
    STATE_ECO: "manualEcoActive",
    STATE_MANUEL: "manualEcoInactive",
    STATE_AUTO: "autoMode",
}
SUPPORT_WATER_HEATER = [STATE_ECO, STATE_AUTO, STATE_MANUEL]

SUPPORT_FLAGS_WATER_HEATER = (
    SUPPORT_OPERATION_MODE | SUPPORT_AWAY_MODE | SUPPORT_TARGET_TEMPERATURE
)

AWAY_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_TIME_PERIOD): cv.positive_int,
    }
)

BOOST_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_TIME_PERIOD): vol.All(
            cv.positive_int, vol.Range(min=0, max=7)
        ),
    }
)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set the sensor platform."""
    datas = hass.data[DOMAIN][config_entry.entry_id][COZYTOUCH_DATAS]

    devices = []
    for water_heater in datas.water_heaters:
        if water_heater.widget == DeviceType.WATER_HEATER:
            devices.append(StandaloneCozytouchWaterHeater(water_heater))

    _LOGGER.info("Found {count} water heater".format(count=len(devices)))
    async_add_entities(devices, True)

    async def async_service_away_mode(service):
        """Handle away mode service."""
        entity_id = service.data.get(ATTR_ENTITY_ID)
        for device in devices:
            if device.entity_id == entity_id:
                await hass.async_add_executor_job(
                    device.async_set_away_mode, service.data[ATTR_TIME_PERIOD]
                )

    async def async_service_boost_mode(service):
        """Handle away mode service."""
        entity_id = service.data.get(ATTR_ENTITY_ID)
        for device in devices:
            if device.entity_id == entity_id:
                await hass.async_add_executor_job(
                    device.async_set_boost_mode, service.data[ATTR_TIME_PERIOD]
                )

    hass.services.async_register(
        DOMAIN, SERVICE_SET_AWAY_MODE, async_service_away_mode, schema=AWAY_MODE_SCHEMA
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_BOOST_MODE,
        async_service_boost_mode,
        schema=BOOST_MODE_SCHEMA,
    )


class StandaloneCozytouchWaterHeater(WaterHeaterDevice):
    """Representation a Water Heater."""

    def __init__(self, water_heater):
        """Initialize the sensor."""
        self.water_heater = water_heater
        self.fetch_datas = None
        self._support_flags = None
        self._target_temperature = None
        self._away = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self.water_heater.name

    @property
    def unique_id(self):
        """Return the name of the sensor."""
        return self.water_heater.id

    def avaibility(self):
        """Return avaibility sensor."""
        return self.water_heater.is_on

    @property
    def target_temperature_high(self):
        """Return the highbound target temperature we try to reach."""
        return self.fetch_datas.get(
            DeviceState.MAX_TEMPERATURE_MANUEL_MODE_STATE.value  # pylint: disable=maybe-no-member
        )

    @property
    def target_temperature_low(self):
        """Return the lowbound target temperature we try to reach."""
        return self.fetch_datas.get(
            DeviceState.MIN_TEMPERATURE_MANUEL_MODE_STATE.value  # pylint: disable=maybe-no-member
        )

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return DEFAULT_MIN_TEMP

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return DEFAULT_MAX_TEMP

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_FLAGS_WATER_HEATER

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def current_operation(self):
        """Return current operation ie. eco, electric, performance, ..."""
        return COZY_TO_HASS_STATE[
            self.fetch_datas.get(
                DeviceState.DHW_MODE_STATE.value  # pylint: disable=maybe-no-member
            )
        ]

    @property
    def operation_list(self):
        """List of available operation modes."""
        return SUPPORT_WATER_HEATER

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self.fetch_datas.get(
            DeviceState.MIDDLE_WATER_TEMPERATURE_STATE.value  # pylint: disable=maybe-no-member
        )

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self.fetch_datas.get(
            DeviceState.TARGET_TEMPERATURE_STATE.value  # pylint: disable=maybe-no-member
        )

    @property
    def is_away_mode_on(self):
        """Return true if away mode is on."""
        om_state = self.fetch_datas.get(
            DeviceState.OPERATING_MODE_STATE.value  # pylint: disable=maybe-no-member
        )
        return om_state["absence"] == STATE_ON

    @property
    def is_boost_mode_on(self):
        """Return true if boost mode is on."""
        om_state = self.fetch_datas.get(
            DeviceState.OPERATING_MODE_STATE.value  # pylint: disable=maybe-no-member
        )
        return om_state["relaunch"] == STATE_ON

    async def async_set_operation_mode(self, operation_mode):
        """Set new target operation mode."""
        await async_make_request(
            self.hass,
            self.water_heater.set_operating_mode,
            HASS_TO_COZY_STATE[operation_mode],
        )
        # await self.hass.async_add_executor_job(
        #     self.water_heater.set_operating_mode, HASS_TO_COZY_STATE[operation_mode]
        # )

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        self._target_temperature = kwargs.get(ATTR_TEMPERATURE)
        await async_make_request(
            self.hass, self.water_heater.set_temperature, self._target_temperature
        )
        # await self.hass.async_add_executor_job(
        #     self.water_heater.set_temperature, self._target_temperature
        # )

    async def async_set_away_mode(self, period):
        """Turn away on."""
        _LOGGER.debug("Set away mode for {} days".format(period))
        await async_make_request(self.hass, self.water_heater.set_away_mode, period)
        # await self.hass.async_add_executor_job(self.water_heater.set_away_mode, period)

    async def async_set_boost_mode(self, period):
        """Turn away on."""
        _LOGGER.debug("Set boost mode for {} days".format(period))
        await async_make_request(self.hass, self.water_heater.set_boost_mode, period)
        # await self.hass.async_add_executor_job(self.water_heater.set_boost_mode, period)

    async def async_turn_boost_mode_off(self):
        """Turn away off."""
        await self.async_set_boost_mode(0)

    async def async_turn_away_mode_on(self):
        """Turn away on."""
        await self.async_set_away_mode(1)

    async def async_turn_away_mode_off(self):
        """Turn away off."""
        await self.async_set_away_mode(0)

    async def async_update(self):
        """Fetch new state data for this sensor."""
        _LOGGER.debug("Update water heater {name}".format(name=self.name))
        await async_make_request(self.hass, self.water_heater.update)
        # try:
        #     await self.hass.async_add_executor_job(self.water_heater.update)
        # except CozytouchException:
        #     _LOGGER.error("Device data no retrieve {}".format(self.name))

        fdatas = {}
        for item in self.water_heater.data.get("states"):
            fdatas.update({item["name"]: item["value"]})
        self.fetch_datas = fdatas

    @property
    def device_info(self):
        """Return the device info."""
        return {
            "name": self.name,
            "identifiers": {(DOMAIN, self.unique_id)},
            "manufacturer": self.water_heater.manufacturer,
            "model": self.fetch_datas.get(
                DeviceState.DHW_CAPACITY_STATE.value  # pylint: disable=maybe-no-member
            ),
            "via_device": (DOMAIN, self.water_heater.data["placeOID"]),
        }

    @property
    def device_state_attributes(self):
        """Return the device state attributes."""
        attributes = {
            "energy_demand": self.fetch_datas.get(
                DeviceState.OPERATING_MODE_CAPABILITIES_STATE.value  # pylint: disable=maybe-no-member
            )["energyDemandStatus"]
            == 1,
            "aways_mode_duration": self.fetch_datas.get(
                DeviceState.AWAY_MODE_DURATION_STATE.value  # pylint: disable=maybe-no-member
            ),
            "boost_mode": self.is_boost_mode_on,
            "boost_mode_duration": self.fetch_datas.get(
                DeviceState.BOOST_MODE_DURATION_STATE.value  # pylint: disable=maybe-no-member
            ),
            "boost_mode_start": self.fetch_datas.get(
                DeviceState.BOOST_START_DATE_STATE.value  # pylint: disable=maybe-no-member
            ),
            "boost_mode_end": self.fetch_datas.get(
                DeviceState.BOOST_END_DATE_STATE.value  # pylint: disable=maybe-no-member
            ),
            "anti_legionellosis": self.fetch_datas.get(
                DeviceState.ANTI_LEGIONELLOSIS_STATE.value  # pylint: disable=maybe-no-member
            ),
            "programmation": self.fetch_datas.get(
                DeviceState.PROGRAMMING_SLOTS_STATE.value  # pylint: disable=maybe-no-member
            ),
            "V40": self.fetch_datas.get(
                DeviceState.V40_WATER_VOLUME_ESTIMATION_STATE.value  # pylint: disable=maybe-no-member
            ),
            "booster_time": self.fetch_datas.get(
                DeviceState.ELECTRIC_BOOSTER_OPERATING_TIME_STATE.value  # pylint: disable=maybe-no-member
            ),
            "heatpump_time": self.fetch_datas.get(
                DeviceState.HEAT_PUMP_OPERATING_TIME_STATE.value  # pylint: disable=maybe-no-member
            ),
            "power_electrical": int(
                self.fetch_datas.get(
                    DeviceState.POWER_HEAT_ELECTRICAL_STATE.value  # pylint: disable=maybe-no-member
                )
            )
            / 1000,
            "power_heatpump": int(
                self.fetch_datas.get(
                    DeviceState.POWER_HEAT_PUMP_STATE.value  # pylint: disable=maybe-no-member
                )
            )
            / 1000,
            "efficiency": round(
                (
                    int(
                        self.fetch_datas.get(
                            DeviceState.HEAT_PUMP_OPERATING_TIME_STATE.value  # pylint: disable=maybe-no-member
                        )
                    )
                    / (
                        int(
                            self.fetch_datas.get(
                                DeviceState.ELECTRIC_BOOSTER_OPERATING_TIME_STATE.value  # pylint: disable=maybe-no-member
                            )
                        )
                        + int(
                            self.fetch_datas.get(
                                DeviceState.HEAT_PUMP_OPERATING_TIME_STATE.value  # pylint: disable=maybe-no-member
                            )
                        )
                    )
                )
                * 100
            ),
            "showers_remaining": self.fetch_datas.get(
                DeviceState.NUM_SHOWER_REMAINING_STATE.value  # pylint: disable=maybe-no-member
            ),
        }

        # Remove attributes is empty
        clean_attributes = {
            k: v for k, v in attributes.items() if (v is not None and v != -1)
        }
        return clean_attributes
