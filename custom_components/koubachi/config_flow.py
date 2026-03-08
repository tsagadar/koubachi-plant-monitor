"""Config flow for the Koubachi Plant Sensor integration."""

from __future__ import annotations

import json
import re

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_CALIBRATION, CONF_KEY, CONF_MAC, DOMAIN

MAC_RE = re.compile(r"^[0-9a-f]{12}$")
KEY_RE = re.compile(r"^[0-9a-fA-F]{32}$")


def _user_schema(defaults: dict | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required("name", default=d.get("name", "")): str,
            vol.Required(CONF_MAC, default=d.get(CONF_MAC, "")): str,
            vol.Required(CONF_KEY, default=d.get(CONF_KEY, "")): str,
            vol.Optional(CONF_CALIBRATION, default=d.get(CONF_CALIBRATION, "{}")): str,
        }
    )


class KoubachiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Koubachi config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            mac = user_input[CONF_MAC].lower().replace(":", "").replace("-", "")
            key = user_input[CONF_KEY].lower()
            calibration_raw = user_input.get(CONF_CALIBRATION, "{}").strip() or "{}"

            if not MAC_RE.match(mac):
                errors[CONF_MAC] = "invalid_mac"
            elif not KEY_RE.match(key):
                errors[CONF_KEY] = "invalid_key"
            else:
                try:
                    calibration = json.loads(calibration_raw)
                    if not isinstance(calibration, dict):
                        raise ValueError("not a dict")
                except json.JSONDecodeError, ValueError:
                    errors[CONF_CALIBRATION] = "invalid_calibration"

            if not errors:
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input["name"],
                    data={
                        CONF_MAC: mac,
                        CONF_KEY: key,
                        CONF_CALIBRATION: calibration_raw,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Allow the user to update name and calibration (MAC and key are fixed)."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        errors: dict[str, str] = {}

        if user_input is not None:
            calibration_raw = user_input.get(CONF_CALIBRATION, "{}").strip() or "{}"
            try:
                calibration = json.loads(calibration_raw)
                if not isinstance(calibration, dict):
                    raise ValueError("not a dict")
            except json.JSONDecodeError, ValueError:
                errors[CONF_CALIBRATION] = "invalid_calibration"

            if not errors:
                self.hass.config_entries.async_update_entry(
                    entry,
                    title=user_input["name"],
                    data={**entry.data, CONF_CALIBRATION: calibration_raw},
                )
                return self.async_abort(reason="reconfigure_successful")

        schema = vol.Schema(
            {
                vol.Required("name", default=entry.title): str,
                vol.Optional(
                    CONF_CALIBRATION,
                    default=entry.data.get(CONF_CALIBRATION, "{}"),
                ): str,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                CONF_MAC: entry.data[CONF_MAC],
            },
        )
