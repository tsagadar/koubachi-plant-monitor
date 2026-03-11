"""HTTP endpoints for Koubachi sensor communication.

The Koubachi sensor talks to api.koubachi.com on port 80, using paths
under /v1/smart_devices/{mac}/. Point that hostname at Home Assistant
via local DNS and these views handle the three endpoints the sensor uses.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CALIBRATION,
    CONF_KEY,
    CONF_MAC,
    CONTENT_TYPE,
    DOMAIN,
    signal_new_reading,
)
from .crypto import decrypt, encrypt
from .sensors import SENSOR_TYPES, convert_reading

_LOGGER = logging.getLogger(__name__)


def _get_device_data(hass: HomeAssistant, mac: str) -> dict | None:
    return hass.data.get(DOMAIN, {}).get(mac)


def _decrypt_body(device_data: dict, raw: bytes) -> str | None:
    """Decrypt, verify CRC and return the plaintext string."""
    key = bytes.fromhex(device_data[CONF_KEY])
    try:
        plaintext = decrypt(key, raw).decode("utf-8")
    except ValueError as exc:
        _LOGGER.warning("Koubachi: decrypt/CRC error: %s", exc)
        return None
    except Exception:
        _LOGGER.exception("Koubachi: unexpected error decrypting body")
        return None
    _LOGGER.info("Koubachi: decrypted body: %r", plaintext)
    return plaintext


def _encrypt_response(device_data: dict, params: dict) -> bytes:
    key = bytes.fromhex(device_data[CONF_KEY])
    body = "&".join(f"{k}={v}" for k, v in params.items())
    return encrypt(key, body.encode("utf-8"))


# Sensor definitions mirrored from koubachi-pyserver sensors.py:
# {sensor_id: (enabled, polling_interval_or_None)}
_SENSORS: dict[int, tuple[bool, int | None]] = {
    1: (False, 3600),
    2: (True, 86400),
    6: (True, None),
    7: (True, 3600),
    8: (True, 3600),
    9: (True, None),
    10: (True, 18000),
    11: (True, None),
    12: (True, None),
    15: (True, 3600),
    29: (True, 3600),
    # Statistics (all disabled)
    4096: (False, None),
    4112: (False, None),
    4113: (False, None),
    4114: (False, None),
    4115: (False, None),
    4116: (False, None),
    4128: (False, None),
    # Errors (all disabled)
    8192: (False, None),
    8193: (False, None),
    8194: (False, None),
    8195: (False, None),
}


def _build_config_response(last_config_change: int) -> dict:
    """Build the device config response matching koubachi-pyserver get_device_config."""
    cfg: dict = {
        "current_time": int(time.time()),
        "transmit_interval": 55202,
        "transmit_app_led": 1,
        "sensor_app_led": 0,
        "day_threshold": 10.0,
    }
    for sensor_id, (enabled, interval) in _SENSORS.items():
        cfg[f"sensor_enabled[{sensor_id}]"] = int(enabled)
    for sensor_id, (enabled, interval) in _SENSORS.items():
        if enabled and interval is not None:
            cfg[f"sensor_polling_interval[{sensor_id}]"] = interval
    return cfg


class KoubachiDeviceView(HomeAssistantView):
    """PUT /v1/smart_devices/{mac} — initial device check-in."""

    url = "/v1/smart_devices/{mac}"
    name = "api:koubachi:device"
    requires_auth = False

    async def put(self, request: web.Request, mac: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        _LOGGER.info("Koubachi: device check-in from %s (peer=%s)", mac, request.remote)

        device_data = _get_device_data(hass, mac)
        if device_data is None:
            _LOGGER.warning("Koubachi: unknown device %s — not configured", mac)
            return web.Response(status=404)

        raw = await request.read()
        _LOGGER.info("Koubachi: check-in body received (%d bytes)", len(raw))
        plaintext = _decrypt_body(device_data, raw)
        if plaintext is None:
            _LOGGER.warning("Koubachi: failed to decrypt check-in body from %s", mac)
            return web.Response(status=400)
        response_params = {
            "current_time": int(time.time()),
            "last_config_change": device_data.get("last_config_change", 1_000_000_000),
        }
        return web.Response(
            body=_encrypt_response(device_data, response_params),
            content_type=CONTENT_TYPE,
        )


class KoubachiConfigView(HomeAssistantView):
    """POST /v1/smart_devices/{mac}/config — device config request."""

    url = "/v1/smart_devices/{mac}/config"
    name = "api:koubachi:config"
    requires_auth = False

    async def post(self, request: web.Request, mac: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        _LOGGER.info("Koubachi: config request from %s (peer=%s)", mac, request.remote)

        device_data = _get_device_data(hass, mac)
        if device_data is None:
            _LOGGER.warning("Koubachi: unknown device %s — not configured", mac)
            return web.Response(status=404)

        raw = await request.read()
        _LOGGER.info("Koubachi: config body received (%d bytes)", len(raw))
        plaintext = _decrypt_body(device_data, raw)
        if plaintext is None:
            _LOGGER.warning("Koubachi: failed to decrypt config body from %s", mac)
            return web.Response(status=400)
        last_config_change = device_data.get("last_config_change", 1_000_000_000)
        response_params = _build_config_response(last_config_change)
        return web.Response(
            body=_encrypt_response(device_data, response_params),
            content_type=CONTENT_TYPE,
        )


class KoubachiReadingsView(HomeAssistantView):
    """POST /v1/smart_devices/{mac}/readings — sensor measurement upload."""

    url = "/v1/smart_devices/{mac}/readings"
    name = "api:koubachi:readings"
    requires_auth = False

    async def post(self, request: web.Request, mac: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        _LOGGER.info("Koubachi: readings from %s (peer=%s)", mac, request.remote)

        device_data = _get_device_data(hass, mac)
        if device_data is None:
            _LOGGER.warning("Koubachi: unknown device %s — not configured", mac)
            return web.Response(status=404)

        raw = await request.read()
        _LOGGER.info("Koubachi: readings body received (%d bytes)", len(raw))
        plaintext = _decrypt_body(device_data, raw)
        if plaintext is None:
            _LOGGER.warning("Koubachi: failed to decrypt readings body from %s", mac)
            return web.Response(status=400)

        if not plaintext:
            _LOGGER.info("Koubachi: empty readings body from %s (no data)", mac)
            data = {}
        else:
            try:
                data = json.loads(plaintext)
            except json.JSONDecodeError:
                _LOGGER.warning(
                    "Koubachi: readings body is not valid JSON from %s: %r",
                    mac,
                    plaintext,
                )
                return web.Response(status=400)

        calibration = device_data.get(CONF_CALIBRATION, {})
        if isinstance(calibration, str):
            try:
                calibration = json.loads(calibration)
            except json.JSONDecodeError:
                calibration = {}

        # Readings format: [[timestamp, sensor_type_id, raw_value], ...]
        # Collect all readings grouped by sensor key so we can record full history.
        readings_by_key: dict[str, list[tuple[int, float, object]]] = defaultdict(list)
        for reading in data.get("readings", []):
            try:
                ts, type_id, raw_value = reading[0], reading[1], reading[2]
            except IndexError, TypeError, ValueError:
                _LOGGER.warning("Koubachi: malformed reading from %s: %s", mac, reading)
                continue

            info = SENSOR_TYPES.get(type_id)
            if info is None:
                _LOGGER.debug("Koubachi: unknown sensor type %s from %s", type_id, mac)
                continue

            converted = convert_reading(type_id, raw_value, calibration)
            if converted is not None:
                readings_by_key[info.key].append((ts, converted, info))

        # Look up the device name for statistic metadata labels.
        entry = next(
            (
                e
                for e in hass.config_entries.async_entries(DOMAIN)
                if e.data.get(CONF_MAC) == mac
            ),  # noqa: E501
            None,
        )
        device_name = entry.title if entry else mac

        for key, readings in readings_by_key.items():
            readings.sort(key=lambda r: r[0])  # oldest → newest
            latest_ts, latest_value, info = readings[-1]

            _LOGGER.info(
                "Koubachi %s: %s = %s %s (measured at %s, %d reading(s) in batch)",
                mac,
                info.key,
                latest_value,
                info.unit,
                latest_ts,
                len(readings),
            )
            # Update the live entity state with the most recent reading.
            async_dispatcher_send(hass, signal_new_reading(mac, info.key), latest_value)

            # Write all readings to recorder statistics with their actual timestamps
            # so that HA history reflects when measurements were actually taken.
            metadata = StatisticMetaData(
                has_mean=True,
                has_sum=False,
                name=f"{device_name} {info.name}",
                source=DOMAIN,
                statistic_id=f"{DOMAIN}:{mac}_{key}",
                unit_of_measurement=info.unit,
            )
            statistics = [
                StatisticData(
                    start=dt_util.utc_from_timestamp(ts).replace(
                        minute=0, second=0, microsecond=0
                    ),
                    mean=value,
                )
                for ts, value, _ in readings
            ]
            async_add_external_statistics(hass, metadata, statistics)

        response_params = {
            "current_time": int(time.time()),
            "last_config_change": device_data.get("last_config_change", 1_000_000_000),
        }
        return web.Response(
            status=201,
            body=_encrypt_response(device_data, response_params),
            content_type=CONTENT_TYPE,
        )
