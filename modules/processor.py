"""
modules/processor.py
--------------------
Phase 3 — ECE Mathematical Engine.
Doppler shift, Free Space Path Loss, and Communication Window logic.
All calculations use SI units internally; helper converters are provided.
"""

import math
import time
import logging
from typing import List, Optional, Tuple

import numpy as np

import config
from modules.models import SatellitePosition, PassEvent, RFAnalysis, GroundStation

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
C = config.SPEED_OF_LIGHT          # m/s
EARTH_RADIUS_KM = 6371.0           # km

# FSPL "readability" threshold — signals above this dB are too attenuated
FSPL_READABLE_THRESHOLD_DB = 142.0


# ── Geometry helpers ──────────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points in kilometres."""
    r = EARTH_RADIUS_KM
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def slant_range_km(
    observer_lat: float,
    observer_lon: float,
    observer_alt_m: float,
    sat_lat: float,
    sat_lon: float,
    sat_alt_km: float,
) -> float:
    """
    3-D slant range (straight-line distance through the atmosphere) in km.
    Uses the law of cosines on the sphere.
    """
    # Observer altitude in km
    obs_alt_km = observer_alt_m / 1000.0
    R_obs = EARTH_RADIUS_KM + obs_alt_km
    R_sat = EARTH_RADIUS_KM + sat_alt_km

    # Central angle between observer and satellite ground track
    phi1, phi2 = math.radians(observer_lat), math.radians(sat_lat)
    lam1, lam2 = math.radians(observer_lon), math.radians(sat_lon)

    central_angle = math.acos(
        min(1.0, max(-1.0,
            math.sin(phi1) * math.sin(phi2)
            + math.cos(phi1) * math.cos(phi2) * math.cos(lam2 - lam1)
        ))
    )

    # Law of cosines
    slant = math.sqrt(
        R_obs ** 2 + R_sat ** 2 - 2 * R_obs * R_sat * math.cos(central_angle)
    )
    return slant


# ── Doppler Shift ─────────────────────────────────────────────────────────────

def doppler_shift(
    carrier_freq_hz: float,
    velocity_km_s: float,
    approaching: bool = True,
) -> Tuple[float, float]:
    """
    Calculate Doppler-shifted frequency.

    Formula:  f_shifted = f_c * (c ± v_rel) / c
      + for approaching (blue-shift)
      − for receding  (red-shift)

    Returns (shift_hz, shifted_freq_hz).
    """
    v_rel = velocity_km_s * 1000.0   # km/s → m/s
    if approaching:
        shifted = carrier_freq_hz * (C + v_rel) / C
    else:
        shifted = carrier_freq_hz * (C - v_rel) / C

    shift = shifted - carrier_freq_hz
    return shift, shifted


# ── Free Space Path Loss ──────────────────────────────────────────────────────

def free_space_path_loss_db(slant_range_km: float, freq_hz: float) -> float:
    """
    FSPL (dB) = 20·log10(d) + 20·log10(f) + 20·log10(4π/c)
    where d is in metres and f in Hz.
    """
    d_m = slant_range_km * 1000.0
    if d_m <= 0:
        return 0.0
    fspl = 20 * math.log10(d_m) + 20 * math.log10(freq_hz) - 147.55
    return fspl


def signal_quality_label(fspl_db: float) -> str:
    """Map FSPL to a human-readable quality string."""
    if fspl_db < 120:
        return "Excellent"
    elif fspl_db < 135:
        return "Good"
    elif fspl_db < FSPL_READABLE_THRESHOLD_DB:
        return "Marginal"
    else:
        return "No Signal"


# ── Communication Window ──────────────────────────────────────────────────────

def communication_window(passes: List[PassEvent]) -> Optional[PassEvent]:
    """Return the next upcoming pass, or None if no passes are scheduled."""
    now = int(time.time())
    upcoming = [p for p in passes if p.aos_timestamp > now]
    if not upcoming:
        return None
    return min(upcoming, key=lambda p: p.aos_timestamp)


def seconds_to_aos(pass_event: PassEvent) -> int:
    """Seconds until Acquisition of Signal for a given pass."""
    return max(0, pass_event.aos_timestamp - int(time.time()))


def seconds_to_los(pass_event: PassEvent) -> int:
    """Seconds until Loss of Signal (negative = already lost)."""
    return pass_event.los_timestamp - int(time.time())


def is_pass_active(pass_event: PassEvent) -> bool:
    """True if we are currently inside the AOS–LOS window."""
    now = int(time.time())
    return pass_event.aos_timestamp <= now <= pass_event.los_timestamp

def link_budget(
    fspl_db: float,
    tx_power_dbm: float = config.TX_POWER_DBM,
    tx_gain_dbi: float = config.TX_ANTENNA_GAIN_DBI,
    rx_gain_dbi: float = config.RX_ANTENNA_GAIN_DBI,
    rx_sensitivity_dbm: float = config.RX_SENSITIVITY_DBM,
) -> Tuple[float, float, bool]:
    received_power = tx_power_dbm + tx_gain_dbi - fspl_db + rx_gain_dbi
    margin = received_power - rx_sensitivity_dbm
    return received_power, margin, margin >= 0

# ── Full RF Analysis for a position snapshot ──────────────────────────────────

def analyse_position(
    pos: SatellitePosition,
    ground: GroundStation,
    carrier_freq_hz: float = config.CARRIER_FREQ_HZ,
    radial_velocity_km_s: float = None,
) -> RFAnalysis:
    """
    Run the full ECE engine on a single SatellitePosition snapshot.
    Uses radial velocity (rate of change of slant range) for Doppler.
    Negative radial velocity = approaching, positive = receding.
    Falls back to API velocity value if radial_velocity_km_s is not provided.
    """
    slant = slant_range_km(
        ground.lat, ground.lon, ground.alt_m,
        pos.lat, pos.lon, pos.alt_km,
    )

    # Use computed radial velocity if available, else fall back to API value
    if radial_velocity_km_s is not None:
        approaching = radial_velocity_km_s < 0
        speed = abs(radial_velocity_km_s)
    else:
        approaching = pos.elevation > 0
        speed = pos.velocity_km_s

    shift_hz, shifted_hz = doppler_shift(
        carrier_freq_hz, speed, approaching
    )

    fspl = free_space_path_loss_db(slant, carrier_freq_hz)
    readable = fspl < FSPL_READABLE_THRESHOLD_DB
    quality = signal_quality_label(fspl)

    received_power, margin, feasible = link_budget(fspl)

    return RFAnalysis(
        doppler_shift_hz=shift_hz,
        shifted_freq_hz=shifted_hz,
        fspl_db=fspl,
        slant_range_km=slant,
        is_readable=readable,
        signal_quality=quality,
        received_power_dbm=round(received_power, 2),
        link_margin_db=round(margin, 2),
        link_feasible=feasible,
)

def analyse_track(
    positions: List[SatellitePosition],
    ground: GroundStation,
    carrier_freq_hz: float = config.CARRIER_FREQ_HZ,
) -> List[RFAnalysis]:
    """
    Run RF analysis over an entire list of positions.
    Computes radial velocity from the rate of change of slant range
    between consecutive snapshots (each 1 second apart), fixing the
    zero-velocity bug caused by the N2YO API not returning velocity data.
    """
    results = []
    for i, pos in enumerate(positions):
        # Compute radial velocity from slant range change between snapshots
        if i == 0:
            radial_vel = None  # no previous point for first snapshot
        else:
            prev = positions[i - 1]
            slant_now = slant_range_km(
                ground.lat, ground.lon, ground.alt_m,
                pos.lat, pos.lon, pos.alt_km,
            )
            slant_prev = slant_range_km(
                ground.lat, ground.lon, ground.alt_m,
                prev.lat, prev.lon, prev.alt_km,
            )
            dt = pos.timestamp - prev.timestamp
            radial_vel = (slant_now - slant_prev) / dt if dt > 0 else None

        results.append(analyse_position(pos, ground, carrier_freq_hz, radial_vel))
    return results


def analyse_track_append(
    new_positions: List[SatellitePosition],
    ground: GroundStation,
    carrier_freq_hz: float = config.CARRIER_FREQ_HZ,
    prev_position: Optional[SatellitePosition] = None,
) -> List[RFAnalysis]:
    """
    Run RF analysis on a new batch of positions.
    Uses prev_position (last position from the previous batch) to compute
    radial velocity for the first snapshot in the new batch.
    """
    results = []
    all_positions = ([prev_position] + new_positions) if prev_position else new_positions
    offset = 1 if prev_position else 0

    for i, pos in enumerate(new_positions):
        idx = i + offset
        if idx == 0:
            radial_vel = None
        else:
            prev = all_positions[idx - 1]
            slant_now = slant_range_km(
                ground.lat, ground.lon, ground.alt_m,
                pos.lat, pos.lon, pos.alt_km,
            )
            slant_prev = slant_range_km(
                ground.lat, ground.lon, ground.alt_m,
                prev.lat, prev.lon, prev.alt_km,
            )
            dt = pos.timestamp - prev.timestamp
            radial_vel = (slant_now - slant_prev) / dt if dt > 0 else None

        results.append(analyse_position(pos, ground, carrier_freq_hz, radial_vel))
    return results


# ── Ground-track array helper (for plotting) ──────────────────────────────────

def positions_to_arrays(
    positions: List[SatellitePosition],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Extract parallel numpy arrays from a position list.
    Returns (lats, lons, alts_km, timestamps).
    """
    lats = np.array([p.lat for p in positions])
    lons = np.array([p.lon for p in positions])
    alts = np.array([p.alt_km for p in positions])
    timestamps = np.array([p.timestamp for p in positions])
    return lats, lons, alts, timestamps
