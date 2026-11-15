from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import classify_type
from .const import ATTR_CONFIG_ENTRY_ID, DOMAIN, SERVICE_REFRESH
from .coordinator import LufopCoordinator, LufopData

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.GEO_LOCATION]

_REFRESH_SCHEMA = vol.Schema({vol.Required(ATTR_CONFIG_ENTRY_ID): str})

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class RuntimeData:
    """Holds the runtime objects for one config entry."""

    coordinator: DataUpdateCoordinator
    cancel_update_listener: Callable


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the refresh action, once for the domain.

    Here rather than with the first entry: an automation that calls it while
    the only entry is still waiting for Lufop should be told that, not that
    the action does not exist.
    """
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        _async_handle_refresh,
        schema=_REFRESH_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up Lufop Radar from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    if config_entry.options:
        # Saving the settings used to leave a second copy of them here, the
        # API key included. Nothing reads it; before the update listener
        # below exists, so that clearing it reloads nothing.
        hass.config_entries.async_update_entry(config_entry, options={})

    coordinator = LufopCoordinator(hass, config_entry)

    # Before anything is fetched, and in manual mode too, where nothing
    # would be fetched at all: this is where a key that has been revoked
    # since setup turns into the dialog asking for a new one.
    await coordinator.async_check_key()

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

    runtime_data: RuntimeData | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if runtime_data is None:
        # Disabled, waiting for Lufop, or waiting for a new key.
        raise ServiceValidationError(f"'{entry.title}' is not loaded")
    coordinator = runtime_data.coordinator
    await coordinator.async_refresh()
    if not coordinator.last_update_success:
        # The coordinator keeps its last list through a failed fetch, and
        # that list used to be handed back as if it were the answer.
        raise HomeAssistantError(
            f"'{entry.title}' could not be refreshed: {coordinator.last_exception}"
        )

    radars = coordinator.data.radars if coordinator.data else []
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
