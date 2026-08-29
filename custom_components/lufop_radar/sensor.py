import logging

from homeassistant.components.sensor import SensorEntity, SensorStateClass
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


class LufopTotalSensor(CoordinatorEntity, SensorEntity):
    """How many radars this area currently reports.

    A SensorEntity, which it has to be for the recorder to keep long-term
    statistics of it: the state class was being put into the attributes,
    where it reads like the real thing and is ignored by the machinery that
    acts on it. The entity asked for statistics and quietly got none.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_icon = "mdi:map-marker-radius"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: LufopCoordinator) -> None:
        super().__init__(coordinator)
        # _attr_*, not self.name/self.unique_id: those are cached_property on
        # Entity, so assigning to them happens to work today but is not the
        # documented way and would break the day they go back to being plain
        # properties. geo_location.py already does it this way.
        self._attr_name = f"Lufop {self.coordinator.displayname} Total"
        # Keyed on the entry rather than on its display name, so that
        # renaming an area keeps the sensor it belongs to - and its history.
        self._attr_unique_id = (
            f"{DOMAIN}-{self.coordinator.config_entry.entry_id}-total"
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self):
        radar_count = len(self.coordinator.data.radars)
        if radar_count > self.coordinator.sensorcount:
            return self.coordinator.sensorcount
        return radar_count

    @property
    def extra_state_attributes(self):
        # The breakdown per town, and nothing else: "state_class" used to
        # sit here too, which is not where anything reads it.
        attrs: dict[str, int] = {}
        for radar in self.coordinator.data.radars:
            city = radar.get("commune") or "?"
            attrs[city] = attrs.get(city, 0) + 1
        return attrs
