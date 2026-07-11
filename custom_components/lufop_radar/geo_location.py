from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import location as location_util
from homeassistant.util import slugify

from .api import classify_type
from .const import DOMAIN, SEARCH_MODE_ROUTE
from .coordinator import LufopCoordinator

_LOGGER = logging.getLogger(__name__)

_ICONS = {
    "fixed": "mdi:cctv",
    "mobile": "mdi:speedometer",
    "redlight": "mdi:traffic-light",
}

# Per Lufop's own API docs: F = Front, B = Back, D = Double sens (both).
_FLASH_DIRECTIONS = {
    "F": "front",
    "B": "back",
    "D": "both",
}


def _sign_picture(content: str, font_size: int = 40) -> str:
    """Build a data-URI SVG of a round EU-style sign (white disc, red ring)
    with the given text/emoji centered - the speed limit for speed cameras,
    a traffic-light emoji for red-light cameras. Used as entity_picture,
    which both the entity's own icon and the map card's marker render, so
    every radar type gets a consistent, actually-visible marker instead of
    relying on MDI icons - the map card was found to not render those at
    all, falling back to text initials of the entity name instead.
    """
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<circle cx="50" cy="50" r="46" fill="white" stroke="#e30613" stroke-width="9"/>'
        f'<text x="50" y="54" font-family="Arial,Helvetica,sans-serif" font-weight="bold" '
        f'font-size="{font_size}" fill="black" text-anchor="middle" dominant-baseline="middle">{content}</text>'
        "</svg>"
    )
    return "data:image/svg+xml," + quote(svg)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the geolocation platform."""
    coordinator: LufopCoordinator = hass.data[DOMAIN][config_entry.entry_id].coordinator

    registry = er.async_get(hass)
    unique_prefix = f"{DOMAIN}-{coordinator.displayname}-"
    known_entities: dict[str, LufopLocationEvent] = {}

    @callback
    def _sync_entities() -> None:
        """Add newly reported radars and remove ones no longer in range."""
        radars = coordinator.data.radars[: coordinator.sensorcount]
        current_ids = {str(radar["ID"]) for radar in radars}
        new_entities = []

        for radar in radars:
            radar_id = str(radar["ID"])
            if radar_id in known_entities:
                known_entities[radar_id].update_from_radar(radar)
            else:
                entity = LufopLocationEvent(coordinator, radar_id, radar)
                known_entities[radar_id] = entity
                new_entities.append(entity)

        # Purge every registry entry for this area that no longer matches a
        # currently reported radar - both entries tracked in `known_entities`
        # this session and leftovers from a previous session. Removing the
        # registry entry directly here (synchronously) avoids the window
        # where a gone radar would otherwise show up as a "restored: true" /
        # unavailable ghost until its own (task-scheduled) teardown runs.
        for entry in list(
            er.async_entries_for_config_entry(registry, config_entry.entry_id)
        ):
            if (
                entry.domain == "geo_location"
                and entry.unique_id.startswith(unique_prefix)
                and entry.unique_id[len(unique_prefix):] not in current_ids
            ):
                known_entities.pop(entry.unique_id[len(unique_prefix):], None)
                registry.async_remove(entry.entity_id)

        if new_entities:
            async_add_entities(new_entities)

    coordinator.async_add_listener(_sync_entities)
    _sync_entities()


class LufopLocationEvent(GeolocationEvent):
    """Represents a single Lufop radar as a geolocation event."""

    _attr_should_poll = False

    def __init__(self, coordinator: LufopCoordinator, radar_id: str, radar: dict) -> None:
        self._coordinator = coordinator
        self._radar_id = radar_id
        # Per-area source (e.g. "lufop_radar_berlin") so each configured area
        # can be selected on its own via the map card's geo_location_sources.
        self._attr_source = f"{DOMAIN}_{slugify(coordinator.displayname)}"
        self._attr_unique_id = f"{DOMAIN}-{coordinator.displayname}-{radar_id}"
        self._attr_unit_of_measurement = UnitOfLength.KILOMETERS
        self._extra_attrs: dict[str, Any] = {}
        self._apply(radar)

    def _apply(self, radar: dict) -> None:
        city = radar.get("commune") or ""
        street = radar.get("voie") or ""
        location_label = ", ".join(part for part in (city, street) if part) or "Radar"
        self._attr_name = f"Lufop {self._coordinator.displayname} {location_label}"
        self._attr_latitude = float(radar["lat"])
        self._attr_longitude = float(radar["lng"])
        radar_type = classify_type(radar)
        self._attr_icon = _ICONS.get(radar_type, "mdi:map-marker-alert")
        if radar_type == "redlight":
            self._attr_entity_picture = _sign_picture("\U0001F6A6", font_size=60)  # 🚦, 50% larger than the speed digits
        elif radar.get("vitesse"):
            self._attr_entity_picture = _sign_picture(radar["vitesse"])
        else:
            self._attr_entity_picture = None
        if self.hass is not None:
            self._attr_distance = self._distance_from_area_center(
                self._attr_latitude, self._attr_longitude
            )
        self._extra_attrs = {
            "area": self._coordinator.displayname,
            "type": radar_type,
            "id": self._radar_id,
            "speed": radar.get("vitesse"),
            "city": radar.get("commune"),
            "street": radar.get("voie"),
            "country": radar.get("pays"),
            "flash_direction": _FLASH_DIRECTIONS.get(radar.get("flash"), radar.get("flash")),
            "azimuth": radar.get("azimut"),
            "updated": radar.get("update"),
        }

    def _distance_from_area_center(self, lat: float, lng: float) -> float | None:
        """Return the distance to the nearest configured reference point:
        the area's center point in area mode, or the closest route waypoint
        in route mode.
        """
        if self._coordinator.search_mode == SEARCH_MODE_ROUTE:
            reference_points = self._coordinator.waypoints
        else:
            reference_points = [self._coordinator.location]

        distances = [
            meters
            for point in reference_points
            if (meters := location_util.distance(point["latitude"], point["longitude"], lat, lng)) is not None
        ]
        if not distances:
            return None
        return self.hass.config.units.length(min(distances), UnitOfLength.METERS)

    async def async_added_to_hass(self) -> None:
        """Calculate distance once the entity has access to hass.config."""
        self._attr_distance = self._distance_from_area_center(
            self._attr_latitude, self._attr_longitude
        )
        self.async_write_ha_state()

    @callback
    def update_from_radar(self, radar: dict) -> None:
        """Refresh this entity's state from newly polled data."""
        self._apply(radar)
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Purge the registry entry so gone radars don't linger as orphans."""
        registry = er.async_get(self.hass)
        if self.entity_id in registry.entities:
            registry.async_remove(self.entity_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._extra_attrs
