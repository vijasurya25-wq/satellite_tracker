"""
tests/test_collector.py
-----------------------
Unit tests for the collector module using mocked HTTP responses.
No real API calls are made.
"""

import time
import pytest
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import modules.collector as collector
from modules.models import TLEData, SatellitePosition, PassEvent


# ── Fixtures ──────────────────────────────────────────────────────────────────

TLE_RESPONSE = {
    "info": {"satname": "ISS (ZARYA)", "satid": 25544},
    "tle": (
        "1 25544U 98067A   24001.50000000  .00016717  00000-0  10270-3 0  9013\r\n"
        "2 25544  51.6435  35.9567 0005960  93.4813 266.6998 15.49820621471123"
    ),
}

POSITIONS_RESPONSE = {
    "info": {"satname": "ISS (ZARYA)", "satid": 25544},
    "positions": [
        {
            "satlatitude": 12.5,
            "satlongitude": 77.3,
            "sataltitude": 421.0,
            "azimuth": 180.0,
            "elevation": 45.0,
            "ra": 120.0,
            "dec": 12.0,
            "timestamp": int(time.time()),
            "velocity": 7.66,
        }
    ],
}

PASSES_RESPONSE = {
    "info": {"satname": "ISS (ZARYA)", "satid": 25544},
    "passes": [
        {
            "startUTC": int(time.time()) + 3600,
            "endUTC": int(time.time()) + 4200,
            "maxEl": 62.0,
            "duration": 600,
        }
    ],
}


def _mock_get(json_data):
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestFetchTLE:
    @patch("modules.collector.requests.get")
    def test_returns_tle_data(self, mock_get):
        mock_get.return_value = _mock_get(TLE_RESPONSE)
        tle = collector.fetch_tle(25544)
        assert isinstance(tle, TLEData)
        assert tle.norad_id == 25544
        assert tle.name == "ISS (ZARYA)"
        assert tle.line1.startswith("1 25544")
        assert tle.line2.startswith("2 25544")

    @patch("modules.collector.requests.get")
    def test_malformed_tle_raises(self, mock_get):
        bad = {"info": {"satname": "TEST"}, "tle": "bad data"}
        mock_get.return_value = _mock_get(bad)
        with pytest.raises(ValueError):
            collector.fetch_tle(99999)


class TestFetchPositions:
    @patch("modules.collector.requests.get")
    def test_returns_position_list(self, mock_get):
        mock_get.return_value = _mock_get(POSITIONS_RESPONSE)
        positions = collector.fetch_positions(25544, 12.97, 77.59, 920)
        assert len(positions) == 1
        p = positions[0]
        assert isinstance(p, SatellitePosition)
        assert p.lat == pytest.approx(12.5)
        assert p.velocity_km_s == pytest.approx(7.66)

    @patch("modules.collector.requests.get")
    def test_empty_positions(self, mock_get):
        empty = {"info": {"satname": "ISS (ZARYA)"}, "positions": []}
        mock_get.return_value = _mock_get(empty)
        assert collector.fetch_positions(25544, 0, 0, 0) == []


class TestFetchPasses:
    @patch("modules.collector.requests.get")
    def test_returns_pass_list(self, mock_get):
        mock_get.return_value = _mock_get(PASSES_RESPONSE)
        passes = collector.fetch_passes(25544, 12.97, 77.59, 920)
        assert len(passes) == 1
        p = passes[0]
        assert isinstance(p, PassEvent)
        assert p.max_elevation == pytest.approx(62.0)
        assert p.duration_s == 600

    @patch("modules.collector.requests.get")
    def test_no_passes(self, mock_get):
        mock_get.return_value = _mock_get({"info": {}, "passes": []})
        assert collector.fetch_passes(25544, 0, 0, 0) == []


class TestRateLimit:
    def test_rate_limit_triggers(self):
        collector._REQUEST_TIMESTAMPS.clear()
        # Fill up to the limit
        now = time.time()
        collector._REQUEST_TIMESTAMPS.extend(
            [now - 10] * collector.MAX_REQUESTS_PER_HOUR
        )
        with pytest.raises(RuntimeError, match="rate limit"):
            collector._check_rate_limit()
        collector._REQUEST_TIMESTAMPS.clear()
