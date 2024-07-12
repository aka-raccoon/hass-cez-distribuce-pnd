import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_DEVICE, CONF_PASSWORD, CONF_USERNAME
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN

_LOGGER = logging.getLogger(name=__name__)


AUTH_SCHEMA = vol.Schema(
    schema={
        vol.Required(schema=CONF_USERNAME): cv.string,
        vol.Required(schema=CONF_PASSWORD): cv.string,
        vol.Required(schema=CONF_DEVICE): cv.string,
        vol.Optional(schema="selenium remote", default=False): cv.boolean,
        vol.Optional(schema="selenium url", default="http://localhost:4444"): cv.string,
        vol.Optional(schema="selenium driver", default="chromedriver"): cv.string,
    }
)


async def validate_auth(username: str, password: str) -> None:
    try:
        # TODO: Validate the username and password.
        ...
    except TypeError as err:
        raise ValueError from err


class CezDistribucePndConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Github Custom config flow."""

    data: dict[str, Any] | None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> Any | config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await validate_auth(
                    username=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                )
            except ValueError:
                errors["base"] = "auth"
            if not errors:
                self.data = user_input
                return self.async_create_entry(
                    title="CEZ Distribuce PND", data=self.data
                )
        return self.async_show_form(
            step_id="user", data_schema=AUTH_SCHEMA, errors=errors
        )
