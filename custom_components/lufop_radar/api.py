import asyncio
import logging
from math import ceil

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.lufop.net/api"
FREE_PLAN_MAX_RESULTS = 200

# The free plan allows 10 requests/minute. This is enforced process-wide (not
# per LufopAPI instance) because a single route-mode poll fires one request
# per sample point, and several config entries can also poll around the same
# time - both would burst past the per-minute cap without a shared throttle.
_MIN_SECONDS_BETWEEN_REQUESTS = 6.5
_rate_limit_lock = asyncio.Lock()
_last_request_time = 0.0


class LufopAPIError(Exception):
    """Raised when the Lufop API can't be reached or returns something unusable."""


class LufopAuthError(LufopAPIError):
    """Raised when the API rejects the key itself.

    Kept apart from every other failure because it is the one a person can
    do something about, and the only one worth interrupting them for: it
    becomes ConfigEntryAuthFailed, which asks for a new key rather than
    retrying one that will never work again.
    """


async def _error_detail(response) -> str:
    """Lufop's own words for why a request failed, where it gives them.

    The error body (e.g. {"error": "country_not_allowed", "message": "..."})
    explains far more than the bare status - free-plan country and quota
    limits both arrive as 4xx and read identically otherwise.
    """
    detail = await response.text()
    try:
        body = await response.json(content_type=None)
        if isinstance(body, dict) and "message" in body:
            return body["message"]
    except ValueError:
        pass  # error body wasn't JSON - fall back to the raw text
    return detail


def classify_type(radar: dict) -> str:
    """Return one of "fixed"/"mobile"/"redlight" for a raw radar record.

    Lufop's read API returns "type" as an internal numeric radar-model ID
    (e.g. "18", "40", "154") with no published mapping to a fixed/mobile/
    red-light category - different numeric IDs can all be plain fixed
    cameras. (Lufop's docs *do* define a "fixe"/"mobile"/"chantier"/"feu"
    string enum, but only for the write API used to submit new radars - it
    doesn't appear in read responses.) The "name" field is the only
    reliably present signal on read, and consistently contains a French
    keyword ("Radar Fixe ...", "Radar Feu Rouge ...", "Radar Mobile ...").

    "Chantier" ("Radar Chantier FR", "Radar de Chantier FR") is Lufop's own
    label for mobile radar units deployed in roadwork zones - it's the only
    non-fixed, non-red-light category some countries (e.g. France) report,
    since they have no separate "Radar Mobile" entries at all. Grouped under
    "mobile" here rather than exposed as its own type.
    """
    name = (radar.get("name") or "").lower()
    if "feu" in name:
        return "redlight"
    if "mobile" in name or "chantier" in name:
        return "mobile"
    return "fixed"


def is_speedless_carpool_lane(radar: dict) -> bool:
    """True for "Covoiturage" (carpool/HOV-lane) cameras with no "vitesse".

    These check lane occupancy, not speed - Lufop's own detail page for such
    a radar shows "Vitesse: -" (confirmed against a live example), it isn't
    a data gap. Not useful for a speed-camera integration, so these are
    dropped unconditionally rather than shown as an unlabelled "fixed" radar.
    """
    name = (radar.get("name") or "").lower()
    return "covoiturage" in name and not radar.get("vitesse")


class LufopAPI:
    """Thin wrapper around the Lufop radar API."""

    def __init__(self, hass: HomeAssistant, api_key: str) -> None:
        self._session = async_get_clientsession(hass)
        self._api_key = api_key

    async def _throttle(self) -> None:
        global _last_request_time
        async with _rate_limit_lock:
            loop = asyncio.get_event_loop()
            wait = _last_request_time + _MIN_SECONDS_BETWEEN_REQUESTS - loop.time()
            if wait > 0:
                await asyncio.sleep(wait)
            _last_request_time = loop.time()

    async def get_meta(self) -> dict:
        """Ask the API about the key itself.

        This is the only call that looks at the key at all. Measured
        against the live API: the radar endpoint answers a wrong key, an
        empty key and no key at all with a plain 200 and real data, for
        every country tried. "format=meta" answers 401 with
        {"error": "unauthorized", ...} instead, and per Lufop's own
        documentation it costs no quota - so it is both the only way to
        find out whether a key is any good and a free one.

        Returns Lufop's document about the key: the plan it belongs to,
        how many calls are left today, and which countries it may ask for.
        """
        await self._throttle()
        params = {"key": self._api_key, "format": "meta"}
        try:
            async with self._session.get(BASE_URL, params=params) as response:
                if response.status in (401, 403):
                    raise LufopAuthError(await _error_detail(response))
                if response.status >= 400:
                    raise LufopAPIError(
                        f"Lufop API returned HTTP {response.status} for the key "
                        f"check: {await _error_detail(response)}"
                    )
                data = await response.json(content_type=None)
        except ClientError as err:
            raise LufopAPIError(f"Failed to reach Lufop API: {err}") from err

        if not isinstance(data, dict):
            raise LufopAPIError("Lufop API returned no information about the key")
        return data

    async def get_radars(
        self, latitude: float, longitude: float, radius_km: float, country: str
    ) -> list[dict]:
        """Fetch radars within radius_km of the given point for one country.

        Lufop's search margin ("m") is documented as roughly 1/10 km per unit,
        so a radius in km is converted to m = radius_km * 10.

        Rounded up, not to nearest. The margin is a whole number, and the
        smallest corridor width the config flow allows - 50m - lands exactly
        on 0.5, which round() resolves to 0: the narrowest search a person
        can ask for was the one that asked for no margin at all. Rounding up
        also keeps every other value from quietly searching less ground than
        was requested, which for a radar warning is the wrong direction to
        err in.
        """
        await self._throttle()
        params = {
            "key": self._api_key,
            "format": "json",
            "pays": country,
            "nbr": str(FREE_PLAN_MAX_RESULTS),
            "q": f"{latitude},{longitude}",
            "m": str(max(1, ceil(radius_km * 10))),
        }
        try:
            async with self._session.get(BASE_URL, params=params) as response:
                if response.status >= 400:
                    message = (
                        f"Lufop API returned HTTP {response.status}: "
                        f"{await _error_detail(response)}"
                    )
                    # A rejected key, told apart from a quota or a country
                    # limit - both also 4xx, and both fixed by waiting or by
                    # changing the entry rather than by a new key. This
                    # endpoint does not check keys today (see get_meta), so
                    # this is here for the day it starts, not because it has
                    # ever been seen to fire.
                    if response.status in (401, 403):
                        raise LufopAuthError(message)
                    raise LufopAPIError(message)
                data = await response.json(content_type=None)
        except ClientError as err:
            raise LufopAPIError(f"Failed to reach Lufop API: {err}") from err

        if data is None:
            # "Nothing in range" comes back as a bare null, not as an
            # empty list - confirmed against the live API, where the same
            # point returns radars at a wider margin and null at a narrow
            # one. Treating it as an error made an empty area look like an
            # outage: every entity of that entry went unavailable. Route
            # mode felt it worst, since it queries one narrow corridor per
            # sample point and most of them legitimately hold no radar at
            # all, so a single empty stretch failed the whole poll.
            return []

        if not isinstance(data, list):
            # The API returns an error object (e.g. {"status": "error", ...})
            # instead of a list of radars when the key/params are rejected.
            message = data.get("message") if isinstance(data, dict) else data
            raise LufopAPIError(f"Lufop API returned an error: {message}")

        return data
