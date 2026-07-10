from dataclasses import dataclass
from datetime import timedelta
import logging
import re

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

from .api import LufopAPI, LufopAPIError
from .const import CONF_BLACKLIST, CONF_COUNTRY, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class LufopData:
    """Holds the current set of radars for this area."""

    radars: list[dict]


class LufopCoordinator(DataUpdateCoordinator):
    """Polls the Lufop API for one configured area."""

    data: LufopData

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        self.location = config_entry.data[CONF_LOCATION]
        self.displayname = config_entry.data[CONF_NAME]
        self.country = config_entry.data[CONF_COUNTRY]
        self.whitelist = config_entry.data[CONF_SELECTOR]
        self.sensorcount = config_entry.data[CONF_COUNT]
        self.types = config_entry.data[CONF_TYPE]

        blacklist_raw = config_entry.data.get(CONF_BLACKLIST, "")
        self.blacklist = {
            radar_id.strip() for radar_id in blacklist_raw.split(",") if radar_id.strip()
        }

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({config_entry.unique_id})",
            update_method=self.async_update_data,
            update_interval=timedelta(seconds=60),
        )

        self.api = LufopAPI(hass, config_entry.data[CONF_API_KEY])

    async def async_update_data(self) -> LufopData:
        """Fetch radars and apply the configured filters."""
        try:
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
                ("fixe", self.types["fixed"]),
                ("mobile", self.types["mobile"]),
                ("chantier", self.types["construction"]),
                ("feu", self.types["redlight"]),
            )
            if enabled
        }
        radars = [r for r in radars if r.get("type") in wanted_types]

        if self.whitelist:
            radars = [
                r for r in radars
                if re.match(self.whitelist, r.get("commune") or "")
            ]

        if self.blacklist:
            radars = [r for r in radars if str(r.get("ID")) not in self.blacklist]

        return LufopData(radars=radars)
