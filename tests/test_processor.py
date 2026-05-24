"""
tests/test_processor.py
-----------------------
Unit tests for the ECE math engine (processor.py).
Run with:  python -m pytest tests/ -v
"""

import time
import math
import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.processor import (
    haversine_km,
    slant_range_km,
    doppler_shift,
    free_space_path_loss_db,
    signal_quality_label,
    communication_window,
    seconds_to_aos,
    is_pass_active,
    FSPL_READABLE_THRESHOLD_DB,
)
from modules.models import PassEvent


# ── Geometry ──────────────────────────────────────────────────────────────────

class TestHaversine:
    def test_same_point_is_zero(self):
        assert haversine_km(0, 0, 0, 0) == pytest.approx(0.0)

    def test_equator_quarter_circle(self):
        # 90° of longitude along equator ≈ 10,007 km
        dist = haversine_km(0, 0, 0, 90)
        assert 9_900 < dist < 10_100

    def test_poles(self):
        dist = haversine_km(-90, 0, 90, 0)
        assert dist == pytest.approx(math.pi * 6371.0, rel=1e-3)


class TestSlantRange:
    def test_directly_overhead(self):
        # Same lat/lon, satellite at 400 km altitude → slant ≈ 400 km
        s = slant_range_km(0, 0, 0, 0, 0, 400)
        assert s == pytest.approx(400.0, rel=1e-3)

    def test_slant_greater_than_altitude(self):
        # Off-nadir → slant must exceed orbital altitude
        s = slant_range_km(12.97, 77.59, 920, 13.5, 79.0, 420)
        assert s > 420


# ── Doppler ───────────────────────────────────────────────────────────────────

class TestDopplerShift:
    FC = 145.800e6   # Hz

    def test_approaching_is_positive_shift(self):
        shift, shifted = doppler_shift(self.FC, 7.66, approaching=True)
        assert shift > 0
        assert shifted > self.FC

    def test_receding_is_negative_shift(self):
        shift, shifted = doppler_shift(self.FC, 7.66, approaching=False)
        assert shift < 0
        assert shifted < self.FC

    def test_zero_velocity_no_shift(self):
        shift, shifted = doppler_shift(self.FC, 0.0)
        assert shift == pytest.approx(0.0, abs=1.0)
        assert shifted == pytest.approx(self.FC, rel=1e-9)

    def test_known_value(self):
        # ISS ~7.66 km/s, f=145.8 MHz → shift ≈ +3,720 Hz (approaching)
        shift, _ = doppler_shift(self.FC, 7.66, approaching=True)
        assert 3_500 < shift < 4_000


# ── FSPL ─────────────────────────────────────────────────────────────────────

class TestFSPL:
    def test_increases_with_distance(self):
        f = 145.8e6
        assert free_space_path_loss_db(500, f) < free_space_path_loss_db(2000, f)

    def test_increases_with_frequency(self):
        d = 1000
        assert free_space_path_loss_db(d, 145.8e6) < free_space_path_loss_db(d, 437e6)

    def test_iss_typical_range(self):
        # ISS at ~500 km slant range, 145.8 MHz → expect ~125–145 dB
        fspl = free_space_path_loss_db(500, 145.8e6)
        assert 125 < fspl < 145

    def test_zero_range_returns_zero(self):
        assert free_space_path_loss_db(0, 145.8e6) == 0.0


class TestSignalQuality:
    def test_excellent(self):
        assert signal_quality_label(100.0) == "Excellent"

    def test_good(self):
        assert signal_quality_label(125.0) == "Good"

    def test_marginal(self):
        assert signal_quality_label(138.0) == "Marginal"

    def test_no_signal(self):
        assert signal_quality_label(160.0) == "No Signal"


# ── Communication Window ──────────────────────────────────────────────────────

def _make_pass(offset_start: int, offset_end: int) -> PassEvent:
    now = int(time.time())
    return PassEvent(
        norad_id=25544,
        name="ISS",
        aos_timestamp=now + offset_start,
        los_timestamp=now + offset_end,
        max_elevation=45.0,
        duration_s=offset_end - offset_start,
    )


class TestCommunicationWindow:
    def test_returns_soonest_future_pass(self):
        passes = [_make_pass(7200, 7800), _make_pass(3600, 4200)]
        nxt = communication_window(passes)
        assert nxt is not None
        assert nxt.aos_timestamp < passes[0].aos_timestamp

    def test_no_future_passes(self):
        old = _make_pass(-3600, -3000)
        assert communication_window([old]) is None

    def test_active_pass_detection(self):
        active = _make_pass(-60, 300)   # started 1 min ago, ends in 5 min
        assert is_pass_active(active)

    def test_future_pass_not_active(self):
        future = _make_pass(600, 900)
        assert not is_pass_active(future)

    def test_seconds_to_aos_positive(self):
        p = _make_pass(120, 300)
        assert 115 < seconds_to_aos(p) <= 120
