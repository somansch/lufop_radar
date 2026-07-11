from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_API_KEY,
    CONF_COUNT,
    CONF_LOCATION,
    CONF_NAME,
    CONF_SELECTOR,
    CONF_TYPE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import LufopAPI, LufopAPIError, classify_type, is_speedless_carpool_lane
from .const import (
    CONF_BLACKLIST,
    CONF_CORRIDOR_WIDTH,
    CONF_COUNTRY,
    CONF_SEARCH_MODE,
    CONF_UPDATE_INTERVAL,
    CONF_WAYPOINTS,
    DOMAIN,
    SEARCH_MODE_AREA,
    SEARCH_MODE_ROUTE,
    UPDATE_INTERVAL_MANUAL,
)
from .route import route_sample_points

_LOGGER = logging.getLogger(__name__)


@dataclass
class LufopData:
    """Holds the current set of radars for this area."""

    radars: list[dict]


class LufopCoordinator(DataUpdateCoordinator):
    """Polls the Lufop API for one configured area or route."""

    data: LufopData

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        self.displayname = config_entry.data[CONF_NAME]
        self.country = config_entry.data[CONF_COUNTRY]
        # .get() with a default: entries created before route mode existed
        # only ever know the "area" (radius) search.
        self.search_mode = config_entry.data.get(CONF_SEARCH_MODE, SEARCH_MODE_AREA)
        if self.search_mode == SEARCH_MODE_ROUTE:
            self.location = None
            self.waypoints = config_entry.data[CONF_WAYPOINTS]
            self.corridor_width = config_entry.data[CONF_CORRIDOR_WIDTH]
        else:
            self.location = config_entry.data[CONF_LOCATION]

        # Comma-separated city names, same syntax as the blacklist.
        whitelist_raw = config_entry.data.get(CONF_SELECTOR, "")
        self.whitelist = {
            city.strip().lower() for city in whitelist_raw.split(",") if city.strip()
        }
        self.sensorcount = config_entry.data[CONF_COUNT]
        self.types = config_entry.data[CONF_TYPE]

        blacklist_raw = config_entry.data.get(CONF_BLACKLIST, "")
        self.blacklist = {
            radar_id.strip() for radar_id in blacklist_raw.split(",") if radar_id.strip()
        }

        calls_per_poll = (
            len(self._route_sample_points()) if self.search_mode == SEARCH_MODE_ROUTE else 1
        )
        # .get() with a fallback: entries saved before this became
        # user-configurable keep their previous (quota-safe) polling
        # behaviour until the user next opens Configure and saves, rather
        # than silently jumping to the new, more aggressive suggested
        # default without their say-so.
        interval_minutes = config_entry.data.get(CONF_UPDATE_INTERVAL)
        if interval_minutes is None:
            interval_minutes = 10 * calls_per_poll
        update_interval = (
            None if interval_minutes == UPDATE_INTERVAL_MANUAL
            else timedelta(minutes=interval_minutes)
        )

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({config_entry.unique_id})",
            update_method=self.async_update_data,
            update_interval=update_interval,
        )

        self.api = LufopAPI(hass, config_entry.data[CONF_API_KEY])

    async def async_update_data(self) -> LufopData:
        """Fetch radars and apply the configured filters."""
        try:
            if self.search_mode == SEARCH_MODE_ROUTE:
                radars = await self._get_route_radars()
            else:
                radars = await self.api.get_radars(
                    latitude=self.location["latitude"],
                    longitude=self.location["longitude"],
                    radius_km=self.location["radius"] / 1000,
                    country=self.country,
                )
        except LufopAPIError as err:
            raise UpdateFailed(f"Error communicating with Lufop API: {err}") from err

        # Lufop has no server-side type filter - every configured type must be
        # requested at once and filtered client-side afterwards.
        wanted_types = {
            radar_type
            for radar_type, enabled in (
                ("fixed", self.types["fixed"]),
                ("mobile", self.types["mobile"]),
                ("redlight", self.types["redlight"]),
            )
            if enabled
        }
        radars = [r for r in radars if classify_type(r) in wanted_types]
        radars = [r for r in radars if not is_speedless_carpool_lane(r)]

        if self.whitelist:
            radars = [
                r for r in radars
                if (r.get("commune") or "").strip().lower() in self.whitelist
            ]

        if self.blacklist:
            radars = [r for r in radars if str(r.get("ID")) not in self.blacklist]

        return LufopData(radars=radars)

    def _route_sample_points(self):
        return route_sample_points(self.waypoints, self.corridor_width)

    async def _get_route_radars(self) -> list[dict]:
        """Query a circle of radius corridor_width around every sample point
        along the route and merge the results, deduplicated by radar ID.
        """
        radars: list[dict] = []
        seen_ids: set[str] = set()
        for lat, lng in self._route_sample_points():
            found = await self.api.get_radars(
                latitude=lat,
                longitude=lng,
                radius_km=self.corridor_width / 1000,
                country=self.country,
            )
            for radar in found:
                radar_id = str(radar.get("ID"))
                if radar_id not in seen_ids:
                    seen_ids.add(radar_id)
                    radars.append(radar)
        return radars
