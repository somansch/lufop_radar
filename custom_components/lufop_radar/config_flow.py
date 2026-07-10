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

from .const import CONF_BLACKLIST, CONF_COUNTRY, COUNTRIES, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _country_selector():
    return selector({"select": {"options": COUNTRIES, "mode": "dropdown"}})


class LufopConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            if CONF_LOCATION not in user_input:
                return self.async_abort(reason="location_missing")

            return self.async_create_entry(
                title=f"Lufop {user_input[CONF_NAME]}",
                data={
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_API_KEY: user_input[CONF_API_KEY],
                    CONF_COUNTRY: user_input[CONF_COUNTRY],
                    CONF_TYPE: user_input[CONF_TYPE],
                    CONF_LOCATION: user_input[CONF_LOCATION],
                    CONF_COUNT: user_input["optional"][CONF_COUNT],
                    CONF_SELECTOR: user_input["optional"][CONF_SELECTOR],
                    CONF_BLACKLIST: user_input["optional"][CONF_BLACKLIST],
                },
            )

        data_schema = {
            vol.Required(CONF_NAME): str,
            vol.Required(CONF_API_KEY): str,
            vol.Required(CONF_COUNTRY): _country_selector(),
        }
        data_schema[CONF_LOCATION] = selector({"location": {"radius": True}})
        data_schema[vol.Required(CONF_TYPE)] = section(
            vol.Schema(
                {
                    vol.Required("fixed", default=True): bool,
                    vol.Required("mobile", default=True): bool,
                    vol.Required("construction", default=False): bool,
                    vol.Required("redlight", default=False): bool,
                }
            ),
            {"collapsed": True},
        )
        data_schema[vol.Required("optional")] = section(
            vol.Schema(
                {
                    vol.Required(CONF_COUNT, default=9): int,
                    vol.Required(CONF_SELECTOR, default=".*"): str,
                    vol.Optional(CONF_BLACKLIST, default=""): str,
                }
            ),
            {"collapsed": True},
        )
        return self.async_show_form(step_id="user", data_schema=vol.Schema(data_schema))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return LufopOptionsFlow(config_entry)


class LufopOptionsFlow(OptionsFlowWithConfigEntry):
    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            if CONF_LOCATION not in user_input:
                user_input[CONF_LOCATION] = self.config_entry.data.get(CONF_LOCATION)

            data = {
                CONF_NAME: self.config_entry.data.get(CONF_NAME),
                CONF_API_KEY: user_input[CONF_API_KEY],
                CONF_COUNTRY: user_input[CONF_COUNTRY],
                CONF_TYPE: user_input[CONF_TYPE],
                CONF_LOCATION: user_input[CONF_LOCATION],
                CONF_COUNT: user_input["optional"][CONF_COUNT],
                CONF_SELECTOR: user_input["optional"][CONF_SELECTOR],
                CONF_BLACKLIST: user_input["optional"][CONF_BLACKLIST],
            }
            self.hass.config_entries.async_update_entry(self._config_entry, data=data)
            return self.async_create_entry(title=self._config_entry.title, data=data)

        data_schema = {
            vol.Required(
                CONF_API_KEY, default=self.config_entry.data.get(CONF_API_KEY)
            ): str,
            vol.Required(
                CONF_COUNTRY, default=self.config_entry.data.get(CONF_COUNTRY)
            ): _country_selector(),
        }
        data_schema[vol.Required(CONF_LOCATION, default=self.config_entry.data.get(CONF_LOCATION))] = selector(
            {"location": {"radius": True}}
        )
        data_schema[vol.Required(CONF_TYPE)] = section(
            vol.Schema(
                {
                    vol.Required(
                        "fixed", default=self.config_entry.data.get(CONF_TYPE)["fixed"]
                    ): bool,
                    vol.Required(
                        "mobile", default=self.config_entry.data.get(CONF_TYPE)["mobile"]
                    ): bool,
                    vol.Required(
                        "construction",
                        default=self.config_entry.data.get(CONF_TYPE)["construction"],
                    ): bool,
                    vol.Required(
                        "redlight",
                        default=self.config_entry.data.get(CONF_TYPE)["redlight"],
                    ): bool,
                }
            ),
            {"collapsed": True},
        )
        data_schema[vol.Required("optional")] = section(
            vol.Schema(
                {
                    vol.Required(
                        CONF_COUNT, default=self.config_entry.data.get(CONF_COUNT)
                    ): int,
                    vol.Required(
                        CONF_SELECTOR, default=self.config_entry.data.get(CONF_SELECTOR)
                    ): str,
                    vol.Optional(
                        CONF_BLACKLIST,
                        default=self.config_entry.data.get(CONF_BLACKLIST, ""),
                    ): str,
                }
            ),
            {"collapsed": True},
        )
        return self.async_show_form(step_id="init", data_schema=vol.Schema(data_schema))
