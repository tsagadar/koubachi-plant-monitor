"""Koubachi sensor type definitions and conversion functions.

Conversion functions ported verbatim from:
  koalatux/koubachi-pyserver/src/koubachi_pyserver/sensors.py

Calibration parameters are device-specific values originally provided by
the Koubachi cloud. Missing parameters default to 0.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature


@dataclass
class SensorTypeInfo:
    key: str
    name: str
    unit: str | None
    device_class: str | None
    state_class: str | None
    convert: Callable[[float, dict], float] | None


# ---------------------------------------------------------------------------
# Conversion functions — verbatim from koubachi-pyserver sensors.py
# ---------------------------------------------------------------------------


def convert_lm94022_temperature(x: float, calibration_parameters: dict) -> float:
    dc_offset = calibration_parameters.get("RN171_SMU_DC_OFFSET", 0)
    gain = calibration_parameters.get("RN171_SMU_GAIN", 0)
    x = (x - dc_offset) * gain * 3.0
    temp_offset = calibration_parameters.get("LM94022_TEMPERATURE_OFFSET", 0)
    x = (
        453.512485591335
        - 163.565776259726 * x
        - 10.5408332222805 * (x**2)
        - temp_offset
        - 273.15
    )
    return x


def convert_sfh3710_light(x: float, calibration_parameters: dict) -> float:
    x = (
        (x - calibration_parameters.get("SFH3710_DC_OFFSET_CORRECTION", 0))
        * calibration_parameters.get("RN171_SMU_GAIN", 0)
        / 20.0
        * 7.2
    )
    x = 3333326.67 * ((abs(x) + x) / 2)
    return round(x)


def convert_soil_moisture(x: float, calibration_parameters: dict) -> float | None:
    soil_moisture_min = calibration_parameters.get("SOIL_MOISTURE_MIN", 0)
    soil_moisture_discontinuity = calibration_parameters.get(
        "SOIL_MOISTURE_DISCONTINUITY", 0
    )
    if soil_moisture_discontinuity == soil_moisture_min:
        # Without calibration the denominator is zero; no meaningful value possible.
        return None
    x = (x - soil_moisture_min) * (
        (8778.25 - 3515.25) / (soil_moisture_discontinuity - soil_moisture_min)
    ) + 3515.25
    # Polynomial from koubachi-pyserver: maps ADC range to pF (soil water tension).
    # pF is the log10 of the water column height (cm) needed to extract water from soil.
    # Higher pF = drier soil. Range 0 (saturated) to ~7 (oven dry).
    pf = (
        8.130159393183e-018 * x**5
        - 0.000000000000259586800701037 * x**4
        + 0.00000000328783014726288 * x**3
        - 0.0000206371829755294 * x**2
        + 0.0646453707101697 * x
        - 79.7740602786336
    )
    pf = max(0.0, min(6.0, pf))

    # Convert pF to percentage for compatibility with Plant Monitor / OpenPlantBook.
    # Map the plant-available water range to 0–100%:
    #   pF 2.0 → 100%  (field capacity: maximum plant-available water after drainage)
    #   pF 4.2 →   0%  (permanent wilting point: plants can no longer extract water)
    # Field capacity is conventionally pF 1.8–2.5 depending on soil type; pF 2.0
    # is used as a practical middle ground for typical potting mixes.
    PF_FIELD_CAPACITY = 2.0
    PF_WILTING_POINT = 4.2
    pct = (PF_WILTING_POINT - pf) / (PF_WILTING_POINT - PF_FIELD_CAPACITY) * 100.0
    return round(max(0.0, min(100.0, pct)))


def convert_tsl2561_light(x: float, _calibration_parameters: dict) -> float:
    x = int(x)
    data0 = float((x >> 16) & 0xFFFE)
    data1 = float(x & 0xFFFE)
    gain = (x >> 16) & 0x1
    int_time = x & 0x1
    if gain == 0x0:
        data0 *= 16
        data1 *= 16
    if int_time == 0x0:
        data0 *= 1 / 0.252
        data1 *= 1 / 0.252
    if data0 == 0 or data1 / data0 > 1.30:
        y = 0.0
    elif data1 / data0 > 0.8:
        y = 0.00146 * data0 - 0.00112 * data1
    elif data1 / data0 > 0.61:
        y = 0.0128 * data0 - 0.0153 * data1
    elif data1 / data0 > 0.50:
        y = 0.0224 * data0 - 0.031 * data1
    else:
        y = 0.0304 * data0 - 0.062 * data0 * (data1 / data0) ** 1.4
    return round(y * 5.0)


def _convert_battery(raw: float, calibration: dict) -> float:
    """Convert raw battery voltage (V) to percentage for 2× AA alkaline cells."""
    pct = (raw - 2.0) / (3.0 - 2.0) * 100.0
    return round(min(max(pct, 0.0), 100.0), 1)


# ---------------------------------------------------------------------------
# Sensor type registry  (type_id → SensorTypeInfo)
# ---------------------------------------------------------------------------

SENSOR_TYPES: dict[int, SensorTypeInfo] = {
    2: SensorTypeInfo(
        key="battery",
        name="Battery",
        unit="%",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        convert=_convert_battery,
    ),
    7: SensorTypeInfo(
        key="temperature",
        name="Temperature",
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        convert=convert_lm94022_temperature,
    ),
    8: SensorTypeInfo(
        key="light",
        name="Light",
        unit="lx",
        device_class=SensorDeviceClass.ILLUMINANCE,
        state_class=SensorStateClass.MEASUREMENT,
        convert=convert_sfh3710_light,
    ),
    9: SensorTypeInfo(
        key="rssi",
        name="RSSI",
        unit="dBm",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        convert=lambda x, _: x,
    ),
    11: SensorTypeInfo(
        key="soil_temperature",
        name="Soil Temperature",
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        convert=lambda x, _: x - 2.5,
    ),
    12: SensorTypeInfo(
        key="soil_moisture",
        name="Soil Moisture",
        unit="%",
        device_class=SensorDeviceClass.MOISTURE,
        state_class=SensorStateClass.MEASUREMENT,
        convert=convert_soil_moisture,
    ),
    15: SensorTypeInfo(
        key="temperature",
        name="Temperature",
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        convert=lambda x, _: -46.85 + 175.72 * x / 2**16,
    ),
    29: SensorTypeInfo(
        key="light",
        name="Light",
        unit="lx",
        device_class=SensorDeviceClass.ILLUMINANCE,
        state_class=SensorStateClass.MEASUREMENT,
        convert=convert_tsl2561_light,
    ),
}

# Deduplicated entity definitions — one per measurement key.
SENSOR_ENTITY_KEYS: dict[str, SensorTypeInfo] = {
    info.key: info for info in SENSOR_TYPES.values()
}


def convert_reading(type_id: int, raw: float, calibration: dict) -> float | None:
    info = SENSOR_TYPES.get(type_id)
    if info is None or info.convert is None:
        return None
    return info.convert(raw, calibration)
