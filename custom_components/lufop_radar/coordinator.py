from dataclasses import dataclass, field
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
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import location as location_util

from .api import (
    LufopAPI,
    LufopAPIError,
    LufopAuthError,
    classify_type,
    is_speedless_carpool_lane,
)
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
from .route import distance_to_route, route_sample_points

_LOGGER = logging.getLogger(__name__)


def _usable(radar) -> bool:
    """A record with an ID and a position. One without them used to stop
    the whole entry's markers from being brought up to date."""
    try:
        float(radar["lat"])
        float(radar["lng"])
    except (KeyError, TypeError, ValueError):
        return False
    return radar.get("ID") not in (None, "")


@dataclass
class LufopData:
    """Holds the current set of radars for this area.

    "radars" is what the entry shows: filtered, nearest first, and no more
    than its maximum - the markers, the count sensor and the refresh
    action's answer are all this one list. "in_range" is every radar that
    passed the filters, shown or not, by ID: a radar that only moves up into
    the list because another one left it was there before, and is not new.
    """

    radars: list[dict]
    in_range: frozenset[str] = field(default_factory=frozenset)


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
        # Never below zero: a negative count, which the form used to take,
        # sliced the list from its end.
        self.sensorcount = max(0, config_entry.data[CONF_COUNT])
        # Whether Lufop has been asked at all since this entry was set up.
        # An entry that only fetches on demand starts with an empty list that
        # says nothing about what is out there - see geo_location.py.
        self.fetched = False
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
            # Entries created before the flow claimed a unique id have none,
            # which rendered every one of them as "lufop_radar (None)" -
            # indistinguishable in the log. The display name is what a person
            # recognises anyway.
            name=f"{DOMAIN} ({config_entry.unique_id or self.displayname})",
            update_method=self.async_update_data,
            update_interval=update_interval,
        )

        # Named rather than left to the context DataUpdateCoordinator would
        # otherwise read it from: ConfigEntryAuthFailed can only open the
        # reauth dialog through the entry it belongs to.
        self.config_entry = config_entry
        self.api = LufopAPI(hass, config_entry.data[CONF_API_KEY])

    async def async_check_key(self) -> None:
        """Verify the API key, and ask for a new one if it is rejected.

        Once per setup rather than on every poll. The radar endpoint never
        looks at the key at all (see LufopAPI.get_meta), so a key that has
        been revoked would otherwise never be noticed - the polls would go
        on succeeding until the day Lufop starts enforcing it, and then
        fail with no explanation. The meta call costs no quota.

        Anything that is not about the key - Lufop down, no network - is
        deliberately let go: an outage is no reason to refuse to load, and
        the poll that follows reports it as what it is.
        """
        try:
            await self.api.get_meta()
        except LufopAuthError as err:
            raise ConfigEntryAuthFailed(f"Lufop rejected the API key: {err}") from err
        except LufopAPIError as err:
            _LOGGER.debug("Could not verify the Lufop API key: %s", err)

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
        except LufopAuthError as err:
            # Not an outage to sit out: no number of retries makes a
            # rejected key work again, so this asks for a new one instead.
            raise ConfigEntryAuthFailed(f"Lufop rejected the API key: {err}") from err
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
        radars = [r for r in radars if _usable(r)]
        radars = [r for r in radars if classify_type(r) in wanted_types]
        radars = [r for r in radars if not is_speedless_carpool_lane(r)]

        if self.whitelist:
            radars = [
                r for r in radars
                if (r.get("commune") or "").strip().lower() in self.whitelist
            ]

        if self.blacklist:
            radars = [r for r in radars if str(r.get("ID")) not in self.blacklist]

        radars = self._within_reach(radars)

        self.fetched = True
        return LufopData(
            radars=radars[: self.sensorcount],
            in_range=frozenset(str(r["ID"]) for r in radars),
        )

    def _within_reach(self, radars: list[dict]) -> list[dict]:
        """What really lies in the circle or the corridor, nearest first.

        Lufop's margin is not a circle of that radius - asked for 3 km, it
        answered with a radar 3.8 km away - and its answer comes in no order
        of distance. Cutting that list at the maximum kept whichever radars
        happened to come first, some of them outside what was drawn.

        A route keeps the order of the way: its radars arrive stretch by
        stretch, from the first waypoint to the last.
        """
        if self.search_mode == SEARCH_MODE_ROUTE:
            return [
                r for r in radars
                if distance_to_route(self.waypoints, float(r["lat"]), float(r["lng"]))
                <= self.corridor_width
            ]

        def from_centre(radar: dict) -> float:
            metres = location_util.distance(
                self.location["latitude"], self.location["longitude"],
                float(radar["lat"]), float(radar["lng"]),
            )
            return float("inf") if metres is None else metres

        measured = sorted(((from_centre(r), r) for r in radars), key=lambda pair: pair[0])
        return [r for metres, r in measured if metres <= self.location["radius"]]

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
