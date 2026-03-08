"""Tests for sensor conversion functions."""

import pytest

from custom_components.koubachi.sensors import (
    convert_reading,
    convert_soil_moisture,
    convert_tsl2561_light,
)

# Calibration parameters matching a real device.
CALIBRATION = {
    "RN171_SMU_GAIN": 0.9,
    "RN171_SMU_DC_OFFSET": 0.05,
    "LM94022_TEMPERATURE_OFFSET": 1.2,
    "SFH3710_DC_OFFSET_CORRECTION": 0.01,
    "SOIL_MOISTURE_MIN": 3445.0,
    "SOIL_MOISTURE_DISCONTINUITY": 9501.31,
}


class TestSoilMoisture:
    # The sensor ADC output increases as soil dries out (higher raw = drier).
    # Values near or below SOIL_MOISTURE_MIN are saturated/wet → 100%.
    # Values well above SOIL_MOISTURE_DISCONTINUITY are very dry → 0%.

    def test_wet_soil_returns_100_percent(self):
        # Raw value at SOIL_MOISTURE_MIN → fully wet (pF at or below field capacity).
        assert convert_soil_moisture(3445.0, CALIBRATION) == 100

    def test_dry_soil_returns_low_percentage(self):
        # Raw value well above SOIL_MOISTURE_DISCONTINUITY → very dry.
        result = convert_soil_moisture(12000.0, CALIBRATION)
        assert result == 0

    def test_mid_range_returns_intermediate_percentage(self):
        # Raw value of 9000 should be in the drying range (~30–50%).
        result = convert_soil_moisture(9000.0, CALIBRATION)
        assert result is not None
        assert 20 <= result <= 50

    def test_result_clamped_to_0(self):
        # Extreme high raw value must not go below 0%.
        assert convert_soil_moisture(99999.0, CALIBRATION) == 0

    def test_result_clamped_to_100(self):
        # Extreme low raw value must not exceed 100%.
        assert convert_soil_moisture(0.0, CALIBRATION) == 100

    def test_returns_integer(self):
        result = convert_soil_moisture(6000.0, CALIBRATION)
        assert isinstance(result, int)

    def test_missing_calibration_returns_none(self):
        # Without calibration both params default to 0 → denominator is 0.
        assert convert_soil_moisture(5000.0, {}) is None

    def test_monotonically_decreasing(self):
        # Higher raw value must produce equal or lower moisture percentage.
        raw_values = [3445, 5000, 7000, 8000, 9000, 10000, 12000]
        results = [convert_soil_moisture(r, CALIBRATION) for r in raw_values]
        for a, b in zip(results, results[1:]):
            assert a >= b


class TestTsl2561Light:
    # Bit layout of the packed integer:
    #   bits [31:17] = data0 (upper 15 bits of upper word, via & 0xFFFE after >> 16)
    #   bit  [16]    = gain flag
    #   bits [15:1]  = data1 (lower 15 bits of lower word, via & 0xFFFE)
    #   bit  [0]     = int_time flag
    # gain=1, int_time=1 → no scaling applied to data0/data1.

    @staticmethod
    def _pack(data0: int, data1: int, gain: int = 1, int_time: int = 1) -> int:
        upper = (data0 & 0xFFFE) | (gain & 0x1)
        lower = (data1 & 0xFFFE) | (int_time & 0x1)
        return (upper << 16) | lower

    def test_zero_data0_returns_zero(self):
        # data0 == 0 → y = 0.0 per spec.
        assert convert_tsl2561_light(0, {}) == 0

    def test_returns_integer(self):
        raw = self._pack(data0=0x1000, data1=0x0400)
        assert isinstance(convert_tsl2561_light(raw, {}), int)

    def test_high_ratio_returns_zero(self):
        # data1 / data0 > 1.30 → y = 0.0
        raw = self._pack(data0=0x0010, data1=0x0020)  # ratio = 2.0
        assert convert_tsl2561_light(raw, {}) == 0

    def test_low_ratio_returns_positive(self):
        # data1 / data0 ≤ 0.50 → uses the bright-light formula → positive lux
        raw = self._pack(data0=0x1000, data1=0x0100)  # ratio = 0.0625
        assert convert_tsl2561_light(raw, {}) > 0


class TestConvertReading:
    def test_unknown_type_returns_none(self):
        assert convert_reading(999, 1.0, {}) is None

    def test_rssi_passthrough(self):
        # Type 9 (RSSI) passes the raw value through unchanged.
        assert convert_reading(9, -65.0, {}) == -65.0

    def test_soil_temperature_offset(self):
        # Type 11 subtracts 2.5 from the raw value.
        assert convert_reading(11, 22.5, {}) == 20.0

    def test_temperature_type15_formula(self):
        # Type 15: -46.85 + 175.72 * x / 2**16
        result = convert_reading(15, 2**16 / 2, {})
        assert result == pytest.approx(-46.85 + 175.72 * 0.5, rel=1e-4)
