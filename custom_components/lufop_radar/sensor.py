import logging

from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LufopCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the total-count sensor."""
    coordinator: LufopCoordinator = hass.data[DOMAIN][config_entry.entry_id].coordinator
    async_add_entities([LufopTotalSensor(coordinator)])


class LufopTotalSensor(CoordinatorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_icon = "mdi:map-marker-radius"

    def __init__(self, coordinator: LufopCoordinator) -> None:
        super().__init__(coordinator)
        self.name = f"Lufop {self.coordinator.displayname} Anzahl"
        self.unique_id = f"{DOMAIN}-{self.coordinator.displayname}-total"

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def state(self):
        radar_count = len(self.coordinator.data.radars)
        if radar_count > self.coordinator.sensorcount:
            return self.coordinator.sensorcount
        return radar_count

    @property
    def extra_state_attributes(self):
        attrs = {"state_class": SensorStateClass.MEASUREMENT}
        for radar in self.coordinator.data.radars:
            city = radar.get("commune") or "?"
            attrs[city] = attrs.get(city, 0) + 1
        return attrs
