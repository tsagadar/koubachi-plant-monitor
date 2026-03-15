"""Koubachi Plant Sensor integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_MAC, DOMAIN
from .http import (
    _SENSOR_POLLING_INTERVAL,
    _TRANSMIT_INTERVAL,
    KoubachiConfigView,
    KoubachiDeviceView,
    KoubachiReadingsView,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

# Views are registered once per HA process lifetime.
_views_registered = False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Koubachi from a config entry."""
    global _views_registered

    mac = entry.data[CONF_MAC]
    _LOGGER.info("Koubachi: setting up entry for %s (entry_id=%s)", mac, entry.entry_id)

    # Keep a config version stamp in the entry so that changing transmit/polling
    # intervals bumps entry.modified_at and forces the sensor to re-fetch config.
    config_version = f"{_TRANSMIT_INTERVAL}/{_SENSOR_POLLING_INTERVAL}"
    if entry.data.get("_config_version") != config_version:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "_config_version": config_version}
        )

    hass.data.setdefault(DOMAIN, {})

    # Determine when this device's config was last changed in HA.
    # Use entry.modified_at if available (HA 2024.x+), else fall back to a
    # fixed date in the past so the sensor always accepts our response.
    try:
        last_config_change = int(entry.modified_at.timestamp())
    except AttributeError:
        last_config_change = 1_000_000_000  # 2001-09-09, safely in the past

    device_data = dict(entry.data)
    device_data["last_config_change"] = last_config_change
    hass.data[DOMAIN][mac] = device_data

    if not _views_registered:
        hass.http.register_view(KoubachiDeviceView)
        hass.http.register_view(KoubachiConfigView)
        hass.http.register_view(KoubachiReadingsView)
        _views_registered = True
        _LOGGER.info("Koubachi: HTTP views registered on HA's HTTP server")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("Koubachi: setup complete for %s", mac)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Koubachi config entry."""
    mac = entry.data[CONF_MAC]
    _LOGGER.info("Koubachi: unloading entry for %s (entry_id=%s)", mac, entry.entry_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(mac, None)

    return unload_ok
