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
from homeassistant.util import location as location_util

from .api import LufopAPI, LufopAPIError, classify_type
from .const import (
    CONF_BLACKLIST,
    CONF_CORRIDOR_WIDTH,
    CONF_COUNTRY,
    CONF_SEARCH_MODE,
    CONF_WAYPOINTS,
    DOMAIN,
    SEARCH_MODE_AREA,
    SEARCH_MODE_ROUTE,
)

_LOGGER = logging.getLogger(__name__)

# Free-plan budget is 200 requests/day. Area mode makes 1 request per poll;
# route mode makes one per sample point. Spacing polls MIN_MINUTES_PER_REQUEST
# apart per request keeps (requests per poll) * (polls per day) around
# 144/day for a single entry - a ~28% safety margin under the daily cap for
# occasional manual refreshes or config-flow saves. Multiple areas/routes on
# the same API key all draw from the same daily budget, so that margin
# shrinks per extra entry.
MIN_MINUTES_PER_REQUEST = 10


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
        update_interval = timedelta(minutes=MIN_MINUTES_PER_REQUEST * calls_per_poll)

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

        if self.whitelist:
            radars = [
                r for r in radars
                if (r.get("commune") or "").strip().lower() in self.whitelist
            ]

        if self.blacklist:
            radars = [r for r in radars if str(r.get("ID")) not in self.blacklist]

        return LufopData(radars=radars)

    def _route_sample_points(self):
        """Interpolate points along the waypoint chain, spaced corridor_width
        apart, so the circular per-point queries below overlap and leave no
        gaps - a "poor man's route search" without a real routing engine.
        Straight lines between waypoints, not actual roads, so a route with
        sharp bends needs waypoints placed on those bends to stay accurate.
        """
        points = [(self.waypoints[0]["latitude"], self.waypoints[0]["longitude"])]
        for start, end in zip(self.waypoints, self.waypoints[1:]):
            segment_length = location_util.distance(
                start["latitude"], start["longitude"], end["latitude"], end["longitude"]
            )
            steps = max(1, int(segment_length // self.corridor_width)) if segment_length else 1
            for step in range(1, steps + 1):
                fraction = step / steps
                points.append((
                    start["latitude"] + (end["latitude"] - start["latitude"]) * fraction,
                    start["longitude"] + (end["longitude"] - start["longitude"]) * fraction,
                ))
        return points

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
