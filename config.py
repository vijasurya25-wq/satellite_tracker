"""
config.py
---------
Central configuration for the Satellite Tracker.
Loads all settings from .env or falls back to safe defaults.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── API ──────────────────────────────────────────────────────────────────────
N2YO_API_KEY: str = os.getenv("N2YO_API_KEY", "CHANGE_ME")
N2YO_BASE_URL: str = "https://api.n2yo.com/rest/v1/satellite"

# ── Ground Station ────────────────────────────────────────────────────────────
GROUND_LAT: float = float(os.getenv("GROUND_LAT", 12.9716))   # Bangalore
GROUND_LON: float = float(os.getenv("GROUND_LON", 77.5946))
GROUND_ALT: float = float(os.getenv("GROUND_ALT", 920))       # metres

# ── Target Satellite ─────────────────────────────────────────────────────────
NORAD_ID: int = int(os.getenv("NORAD_ID", 25544))             # ISS

# ── Physics / RF ─────────────────────────────────────────────────────────────
CARRIER_FREQ_HZ: float = float(os.getenv("CARRIER_FREQ_MHZ", 145.800)) * 1e6
SPEED_OF_LIGHT: float = 3.0e8                                  # m/s

# ── Polling ───────────────────────────────────────────────────────────────────
POSITION_SECONDS: int = 300   # seconds of position data per API call (batched)
PASS_DAYS: int = 2            # days ahead to fetch pass predictions
MIN_ELEVATION: int = 10       # degrees — ignore passes below this

# ── Visualization ─────────────────────────────────────────────────────────────
REFRESH_INTERVAL: int = 5     # seconds between console refreshes
MAP_STYLE: str = "dark"       # "dark" | "light"


GEONAMES_USERNAME = os.getenv("GEONAMES_USERNAME", "demo")

TX_POWER_DBM        = float(os.getenv("TX_POWER_DBM", 30.0))
TX_ANTENNA_GAIN_DBI = float(os.getenv("TX_ANTENNA_GAIN_DBI", 2.15))
RX_ANTENNA_GAIN_DBI = float(os.getenv("RX_ANTENNA_GAIN_DBI", 6.0))
RX_SENSITIVITY_DBM  = float(os.getenv("RX_SENSITIVITY_DBM", -120.0))