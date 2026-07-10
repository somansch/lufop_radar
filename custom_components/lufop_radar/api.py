import logging

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.lufop.net/api"


class LufopAPIError(Exception):
    """Raised when the Lufop API can't be reached or returns something unusable."""


class LufopAPI:
    """Thin wrapper around the Lufop radar API."""

    def __init__(self, hass: HomeAssistant, api_key: str) -> None:
        self._session = async_get_clientsession(hass)
        self._api_key = api_key

    async def get_radars(
        self, latitude: float, longitude: float, radius_km: float, country: str
    ) -> list[dict]:
        """Fetch radars within radius_km of the given point for one country.

        Lufop's search margin ("m") is documented as roughly 1/10 km per unit,
        so a radius in km is converted to m = radius_km * 10.
        """
        params = {
            "key": self._api_key,
            "format": "json",
            "pays": country,
            "nbr": "100",  # free-plan maximum per call
            "q": f"{latitude},{longitude}",
            "m": str(round(radius_km * 10)),
        }
        try:
            async with self._session.get(BASE_URL, params=params) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
        except ClientError as err:
            raise LufopAPIError(f"Failed to reach Lufop API: {err}") from err

        if not isinstance(data, list):
            # The API returns an error object (e.g. {"status": "error", ...})
            # instead of a list of radars when the key/params are rejected.
            message = data.get("message") if isinstance(data, dict) else data
            raise LufopAPIError(f"Lufop API returned an error: {message}")

        return data
