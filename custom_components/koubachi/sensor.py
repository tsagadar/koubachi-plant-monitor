"""Koubachi sensor platform – one entity per sensor type per device."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import RestoreSensor, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_MAC, DOMAIN, signal_new_reading
from .sensors import SENSOR_ENTITY_KEYS, SensorTypeInfo

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Koubachi sensors for a config entry."""
    mac = entry.data[CONF_MAC]
    name = entry.title

    entities = [
        KoubachiSensor(mac, name, info)
        for info in SENSOR_ENTITY_KEYS.values()
    ]
    async_add_entities(entities)


class KoubachiSensor(RestoreSensor):
    """Represents a single measurement channel from a Koubachi plant sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        mac: str,
        device_name: str,
        info: SensorTypeInfo,
    ) -> None:
        self._mac = mac
        self._info = info

        self._attr_unique_id = f"koubachi_{mac}_{info.key}"
        self._attr_name = info.name
        self._attr_native_unit_of_measurement = info.unit
        self._attr_device_class = info.device_class
        self._attr_state_class = info.state_class
        self._attr_native_value = None
        self._attr_available = False

        self._attr_device_info = {
            "identifiers": {(DOMAIN, mac)},
            "name": device_name,
            "manufacturer": "Koubachi",
            "model": "Plant Sensor",
        }

    async def async_added_to_hass(self) -> None:
        """Restore last known state and subscribe to new readings."""
        if (last_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last_data.native_value
            self._attr_available = True

        signal = signal_new_reading(self._mac, self._info.key)
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._handle_new_reading)
        )

    @callback
    def _handle_new_reading(self, value: float) -> None:
        self._attr_native_value = value
        self._attr_available = True
        self.async_write_ha_state()
