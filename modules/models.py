"""
modules/models.py
-----------------
Dataclasses that act as the canonical data shapes throughout the project.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class GroundStation:
    lat: float
    lon: float
    alt_m: float
    name: str = "Ground Station"


@dataclass
class TLEData:
    norad_id: int
    name: str
    line1: str
    line2: str


@dataclass
class SatellitePosition:
    """One position snapshot from the N2YO positions endpoint."""
    norad_id: int
    name: str
    timestamp: int          # Unix epoch
    lat: float
    lon: float
    alt_km: float
    azimuth: float          # degrees (0–360)
    elevation: float        # degrees (-90 – +90)
    ra: float               # right ascension
    dec: float              # declination
    velocity_km_s: float    # km/s


@dataclass
class PassEvent:
    """Represents one overhead pass (AOS → LOS)."""
    norad_id: int
    name: str
    aos_timestamp: int      # Acquisition of Signal (Unix)
    los_timestamp: int      # Loss of Signal (Unix)
    max_elevation: float    # peak elevation during pass (degrees)
    duration_s: int         # total pass length in seconds


@dataclass
class RFAnalysis:
    """Results of the ECE math engine for a single position snapshot."""
    doppler_shift_hz: float         # Hz
    shifted_freq_hz: float          # Hz
    fspl_db: float                  # Free Space Path Loss in dB
    slant_range_km: float           # km
    is_readable: bool               # True if FSPL < threshold
    signal_quality: str             # "Excellent" / "Good" / "Marginal" / "No Signal"


@dataclass
class TrackSession:
    """Aggregated data for a full tracking session."""
    ground_station: GroundStation
    tle: Optional[TLEData] = None
    positions: List[SatellitePosition] = field(default_factory=list)
    passes: List[PassEvent] = field(default_factory=list)
    rf_analyses: List[RFAnalysis] = field(default_factory=list)
