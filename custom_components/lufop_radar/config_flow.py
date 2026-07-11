import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlowWithConfigEntry
from homeassistant.const import (
    CONF_API_KEY,
    CONF_COUNT,
    CONF_LOCATION,
    CONF_NAME,
    CONF_SELECTOR,
    CONF_TYPE,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import selector

from .const import (
    CONF_BLACKLIST,
    CONF_CORRIDOR_WIDTH,
    CONF_COUNTRY,
    CONF_SEARCH_MODE,
    CONF_WAYPOINTS,
    COUNTRIES,
    COUNTRY_ORDER_BY_LANGUAGE,
    DEFAULT_CORRIDOR_WIDTH,
    DOMAIN,
    SEARCH_MODE_AREA,
    SEARCH_MODE_ROUTE,
)

_LOGGER = logging.getLogger(__name__)


def _country_selector(language: str = "en"):
    # The option *order* has to be picked here in Python - the frontend
    # renders each option's translated label via translation_key, but never
    # re-sorts the list itself, so an unordered/English-ordered list would
    # look "wrong" in every other language.
    options = COUNTRY_ORDER_BY_LANGUAGE.get(language, COUNTRIES)
    return selector(
        {
            "select": {
                "options": options,
                "translation_key": "country",
                "mode": "dropdown",
            }
        }
    )


def _type_section(defaults: dict | None = None):
    """Radar-type checkboxes shared by the area and route branches."""
    defaults = defaults or {}
    return section(
        vol.Schema(
            {
                vol.Required("fixed", default=defaults.get("fixed", True)): bool,
                vol.Required("mobile", default=defaults.get("mobile", True)): bool,
                vol.Required("redlight", default=defaults.get("redlight", False)): bool,
            }
        ),
        {"collapsed": True},
    )


def _optional_section(defaults: dict | None = None):
    """Whitelist/blacklist/count options shared by the area and route branches."""
    defaults = defaults or {}
    return section(
        vol.Schema(
            {
                vol.Required(CONF_COUNT, default=defaults.get(CONF_COUNT, 9)): int,
                # vol.Optional with description={"suggested_value": ...} instead
                # of default=...: default= reappears whenever the field is
                # cleared back to empty, because the frontend omits an empty
                # *Optional* text field from the submitted payload and
                # voluptuous then re-fills it from the schema default.
                # suggested_value only pre-fills the displayed text and isn't
                # re-applied on submit.
                vol.Optional(CONF_SELECTOR, description={"suggested_value": defaults.get(CONF_SELECTOR, "")}): str,
                vol.Optional(CONF_BLACKLIST, description={"suggested_value": defaults.get(CONF_BLACKLIST, "")}): str,
            }
        ),
        {"collapsed": True},
    )


def _waypoint_schema(default_location: dict):
    # The location selector needs an explicit default: on any step after the
    # flow's very first one, the frontend can't compute an initial value for
    # it on its own and throws, leaving the whole form blank instead of just
    # that field.
    #
    # add_another always defaults to True (not just below the 2-waypoint
    # minimum): defaulting it to False once the minimum is reached would make
    # the wizard silently stop after the 3rd waypoint for anyone who didn't
    # notice the checkbox had flipped and just kept submitting.
    return vol.Schema(
        {
            vol.Required(CONF_LOCATION, default=default_location): selector({"location": {}}),
            vol.Required("add_another", default=True): bool,
        }
    )


def _waypoint_review_schema(default_location: dict):
    """One already-saved waypoint: reposition it or drop it from the route."""
    return vol.Schema(
        {
            vol.Required(CONF_LOCATION, default=default_location): selector({"location": {}}),
            vol.Required("remove", default=False): bool,
        }
    )


def _area_schema(location_default, api_key_default="", country_default=None, type_defaults=None, optional_defaults=None, language="en"):
    return vol.Schema(
        {
            vol.Required(CONF_LOCATION, default=location_default): selector({"location": {"radius": True}}),
            vol.Required(CONF_API_KEY, default=api_key_default): str,
            vol.Required(CONF_COUNTRY, default=country_default): _country_selector(language),
            vol.Required(CONF_TYPE): _type_section(type_defaults),
            vol.Required("optional"): _optional_section(optional_defaults),
        }
    )


def _route_options_schema(corridor_width_default, api_key_default="", country_default=None, type_defaults=None, optional_defaults=None, language="en"):
    return vol.Schema(
        {
            vol.Required(CONF_CORRIDOR_WIDTH, default=corridor_width_default): vol.All(
                vol.Coerce(int), vol.Range(min=50, max=5000)
            ),
            vol.Required(CONF_API_KEY, default=api_key_default): str,
            vol.Required(CONF_COUNTRY, default=country_default): _country_selector(language),
            vol.Required(CONF_TYPE): _type_section(type_defaults),
            vol.Required("optional"): _optional_section(optional_defaults),
        }
    )


class LufopConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._name: str | None = None
        self._waypoints: list[dict] = []

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._name = user_input[CONF_NAME]
            if user_input[CONF_SEARCH_MODE] == SEARCH_MODE_ROUTE:
                self._waypoints = []
                return await self.async_step_waypoint()
            return await self.async_step_area()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_SEARCH_MODE, default=SEARCH_MODE_AREA): selector(
                    {
                        "select": {
                            "options": [SEARCH_MODE_AREA, SEARCH_MODE_ROUTE],
                            "translation_key": "search_mode",
                            "mode": "list",
                        }
                    }
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=data_schema, last_step=False)

    async def async_step_area(self, user_input=None):
        if user_input is not None:
            if CONF_LOCATION not in user_input:  # default location
                return self.async_abort(reason="location_missing")

            return self.async_create_entry(title=f"Lufop {self._name}", data={
                CONF_NAME: self._name,
                CONF_SEARCH_MODE: SEARCH_MODE_AREA,
                CONF_LOCATION: user_input[CONF_LOCATION],
                CONF_API_KEY: user_input[CONF_API_KEY],
                CONF_COUNTRY: user_input[CONF_COUNTRY],
                CONF_TYPE: user_input[CONF_TYPE],
                CONF_COUNT: user_input["optional"][CONF_COUNT],
                CONF_SELECTOR: user_input["optional"].get(CONF_SELECTOR, ""),
                CONF_BLACKLIST: user_input["optional"].get(CONF_BLACKLIST, ""),
            })

        data_schema = _area_schema({
            "latitude": self.hass.config.latitude,
            "longitude": self.hass.config.longitude,
            "radius": 1000,
        }, language=self.hass.config.language)
        return self.async_show_form(step_id="area", data_schema=data_schema, last_step=True)

    async def async_step_waypoint(self, user_input=None):
        errors = {}
        if user_input is not None:
            self._waypoints.append({
                "latitude": user_input[CONF_LOCATION]["latitude"],
                "longitude": user_input[CONF_LOCATION]["longitude"],
            })
            if not user_input["add_another"]:
                if len(self._waypoints) < 2:
                    errors["base"] = "route_needs_two_waypoints"
                else:
                    return await self.async_step_route_options()

        default_location = self._waypoints[-1] if self._waypoints else {
            "latitude": self.hass.config.latitude,
            "longitude": self.hass.config.longitude,
        }
        return self.async_show_form(
            step_id="waypoint",
            data_schema=_waypoint_schema(default_location),
            errors=errors,
            description_placeholders={"count": str(len(self._waypoints) + 1)},
            last_step=False,
        )

    async def async_step_route_options(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title=f"Lufop {self._name}", data={
                CONF_NAME: self._name,
                CONF_SEARCH_MODE: SEARCH_MODE_ROUTE,
                CONF_WAYPOINTS: self._waypoints,
                CONF_CORRIDOR_WIDTH: user_input[CONF_CORRIDOR_WIDTH],
                CONF_API_KEY: user_input[CONF_API_KEY],
                CONF_COUNTRY: user_input[CONF_COUNTRY],
                CONF_TYPE: user_input[CONF_TYPE],
                CONF_COUNT: user_input["optional"][CONF_COUNT],
                CONF_SELECTOR: user_input["optional"].get(CONF_SELECTOR, ""),
                CONF_BLACKLIST: user_input["optional"].get(CONF_BLACKLIST, ""),
            })

        return self.async_show_form(
            step_id="route_options",
            data_schema=_route_options_schema(DEFAULT_CORRIDOR_WIDTH, language=self.hass.config.language),
            last_step=True,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return LufopOptionsFlow(config_entry)


class LufopOptionsFlow(OptionsFlowWithConfigEntry):
    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry
        self._waypoints: list[dict] = []
        self._existing_waypoints: list[dict] = []
        self._review_index: int = 0

    async def async_step_init(self, user_input=None):
        mode = self.config_entry.data.get(CONF_SEARCH_MODE, SEARCH_MODE_AREA)
        if mode == SEARCH_MODE_ROUTE:
            # Editing waypoints is a multi-screen wizard, so it's split from
            # the corridor/type/optional settings behind a menu - otherwise
            # anyone wanting to tweak just the corridor width would first
            # have to click through every saved waypoint to get there.
            return self.async_show_menu(
                step_id="init",
                menu_options=["edit_waypoints", "edit_settings"],
            )
        return await self.async_step_area()

    async def async_step_edit_waypoints(self, user_input=None):
        self._waypoints = []
        self._existing_waypoints = list(self.config_entry.data.get(CONF_WAYPOINTS, []))
        self._review_index = 0
        if self._existing_waypoints:
            return await self.async_step_waypoint_review()
        return await self.async_step_waypoint()

    async def async_step_edit_settings(self, user_input=None):
        # Keep the route's waypoints untouched; only route_options's fields
        # (corridor width, API key/country, types, filters) are being edited.
        self._waypoints = list(self.config_entry.data.get(CONF_WAYPOINTS, []))
        return await self.async_step_route_options()

    async def async_step_waypoint_review(self, user_input=None):
        """Step through the route's already-saved waypoints one at a time,
        so each can be repositioned or dropped before any new ones are
        appended - editing a route no longer means redrawing it from
        scratch.
        """
        if user_input is not None:
            if not user_input["remove"]:
                self._waypoints.append({
                    "latitude": user_input[CONF_LOCATION]["latitude"],
                    "longitude": user_input[CONF_LOCATION]["longitude"],
                })
            self._review_index += 1

        if self._review_index >= len(self._existing_waypoints):
            return await self.async_step_waypoint()

        return self.async_show_form(
            step_id="waypoint_review",
            data_schema=_waypoint_review_schema(self._existing_waypoints[self._review_index]),
            description_placeholders={
                "index": str(self._review_index + 1),
                "total": str(len(self._existing_waypoints)),
            },
            last_step=False,
        )

    async def async_step_area(self, user_input=None):
        if user_input is not None:
            if CONF_LOCATION not in user_input:  # default location
                user_input[CONF_LOCATION] = self.config_entry.data.get(CONF_LOCATION)

            data = {
                CONF_NAME: self.config_entry.data.get(CONF_NAME),
                CONF_SEARCH_MODE: SEARCH_MODE_AREA,
                CONF_LOCATION: user_input[CONF_LOCATION],
                CONF_API_KEY: user_input[CONF_API_KEY],
                CONF_COUNTRY: user_input[CONF_COUNTRY],
                CONF_TYPE: user_input[CONF_TYPE],
                CONF_COUNT: user_input["optional"][CONF_COUNT],
                CONF_SELECTOR: user_input["optional"].get(CONF_SELECTOR, ""),
                CONF_BLACKLIST: user_input["optional"].get(CONF_BLACKLIST, ""),
            }
            self.hass.config_entries.async_update_entry(self._config_entry, data=data)
            return self.async_create_entry(title=self._config_entry.title, data=data)

        data_schema = _area_schema(
            self.config_entry.data.get(CONF_LOCATION),
            api_key_default=self.config_entry.data.get(CONF_API_KEY, ""),
            country_default=self.config_entry.data.get(CONF_COUNTRY),
            type_defaults=self.config_entry.data.get(CONF_TYPE),
            optional_defaults={
                CONF_COUNT: self.config_entry.data.get(CONF_COUNT),
                CONF_SELECTOR: self.config_entry.data.get(CONF_SELECTOR, ""),
                CONF_BLACKLIST: self.config_entry.data.get(CONF_BLACKLIST, ""),
            },
            language=self.hass.config.language,
        )
        return self.async_show_form(step_id="area", data_schema=data_schema, last_step=True)

    async def async_step_waypoint(self, user_input=None):
        errors = {}
        if user_input is not None:
            self._waypoints.append({
                "latitude": user_input[CONF_LOCATION]["latitude"],
                "longitude": user_input[CONF_LOCATION]["longitude"],
            })
            if not user_input["add_another"]:
                if len(self._waypoints) < 2:
                    errors["base"] = "route_needs_two_waypoints"
                else:
                    return await self.async_step_route_options()

        default_location = self._waypoints[-1] if self._waypoints else {
            "latitude": self.hass.config.latitude,
            "longitude": self.hass.config.longitude,
        }
        return self.async_show_form(
            step_id="waypoint",
            data_schema=_waypoint_schema(default_location),
            errors=errors,
            description_placeholders={"count": str(len(self._waypoints) + 1)},
            last_step=False,
        )

    async def async_step_route_options(self, user_input=None):
        if user_input is not None:
            data = {
                CONF_NAME: self.config_entry.data.get(CONF_NAME),
                CONF_SEARCH_MODE: SEARCH_MODE_ROUTE,
                CONF_WAYPOINTS: self._waypoints,
                CONF_CORRIDOR_WIDTH: user_input[CONF_CORRIDOR_WIDTH],
                CONF_API_KEY: user_input[CONF_API_KEY],
                CONF_COUNTRY: user_input[CONF_COUNTRY],
                CONF_TYPE: user_input[CONF_TYPE],
                CONF_COUNT: user_input["optional"][CONF_COUNT],
                CONF_SELECTOR: user_input["optional"].get(CONF_SELECTOR, ""),
                CONF_BLACKLIST: user_input["optional"].get(CONF_BLACKLIST, ""),
            }
            self.hass.config_entries.async_update_entry(self._config_entry, data=data)
            return self.async_create_entry(title=self._config_entry.title, data=data)

        return self.async_show_form(
            step_id="route_options",
            data_schema=_route_options_schema(
                self.config_entry.data.get(CONF_CORRIDOR_WIDTH, DEFAULT_CORRIDOR_WIDTH),
                api_key_default=self.config_entry.data.get(CONF_API_KEY, ""),
                country_default=self.config_entry.data.get(CONF_COUNTRY),
                type_defaults=self.config_entry.data.get(CONF_TYPE),
                optional_defaults={
                    CONF_COUNT: self.config_entry.data.get(CONF_COUNT),
                    CONF_SELECTOR: self.config_entry.data.get(CONF_SELECTOR, ""),
                    CONF_BLACKLIST: self.config_entry.data.get(CONF_BLACKLIST, ""),
                },
                language=self.hass.config.language,
            ),
            last_step=True,
        )
