from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import classify_type
from .const import ATTR_CONFIG_ENTRY_ID, DOMAIN, SERVICE_REFRESH
from .coordinator import LufopCoordinator, LufopData

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.GEO_LOCATION]

_REFRESH_SCHEMA = vol.Schema({vol.Required(ATTR_CONFIG_ENTRY_ID): str})


@dataclass
class RuntimeData:
    """Holds the runtime objects for one config entry."""

    coordinator: DataUpdateCoordinator
    cancel_update_listener: Callable


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up Lufop Radar from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = LufopCoordinator(hass, config_entry)
    if coordinator.update_interval is None:
        # Manual-only (update_interval configured as 0): entities start
        # empty rather than making an API call on every startup/reload -
        # the whole point of choosing manual mode is avoiding automatic
        # requests. Use the "Lufop Refresh" service to populate them.
        coordinator.async_set_updated_data(LufopData(radars=[]))
    else:
        await coordinator.async_config_entry_first_refresh()

    cancel_update_listener = config_entry.add_update_listener(_async_update_listener)

    hass.data[DOMAIN][config_entry.entry_id] = RuntimeData(
        coordinator, cancel_update_listener
    )

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    # Registered once for the domain, not per entry - guarded since
    # async_setup_entry runs again for every additional area/route.
    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH,
            _async_handle_refresh,
            schema=_REFRESH_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )

    return True


async def _async_handle_refresh(call: ServiceCall) -> ServiceResponse:
    """Immediately poll one area/route, e.g. from an automation, instead of
    waiting for its next scheduled poll - the point of "update_interval: 0"
    (fully manual polling), but works just as well as an on-demand refresh
    for entries that do poll automatically. Returns the freshly fetched
    radars so an automation can use them directly (e.g. in a notification)
    without a separate template step to read the resulting entity states.
    """
    hass = call.hass
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(f"'{entry_id}' is not a Lufop Radar config entry")

    runtime_data: RuntimeData = hass.data[DOMAIN][entry.entry_id]
    await runtime_data.coordinator.async_refresh()

    radars = runtime_data.coordinator.data.radars if runtime_data.coordinator.data else []
    return {
        "radars": [
            {
                "id": str(radar.get("ID")),
                "type": classify_type(radar),
                "city": radar.get("commune"),
                "street": radar.get("voie"),
                "speed": radar.get("vitesse"),
                "latitude": radar.get("lat"),
                "longitude": radar.get("lng"),
            }
            for radar in radars
        ]
    }


async def _async_update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle config options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data[DOMAIN][config_entry.entry_id].cancel_update_listener()

    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok
