"""
modules/collector.py
--------------------
Phase 2 — Data Ingestion.
All N2YO REST API calls live here. Rate-limit awareness is built in.
"""

import time
import logging
from typing import List, Optional

import requests

import config
from modules.models import TLEData, SatellitePosition, PassEvent

logger = logging.getLogger(__name__)

# ── Simple in-process rate-limit tracker ─────────────────────────────────────
_REQUEST_TIMESTAMPS: List[float] = []
MAX_REQUESTS_PER_HOUR = 950          # stay 50 below hard limit


def _check_rate_limit() -> None:
    """Remove timestamps older than 1 hour; raise if limit reached."""
    now = time.time()
    hour_ago = now - 3600
    _REQUEST_TIMESTAMPS[:] = [t for t in _REQUEST_TIMESTAMPS if t > hour_ago]
    if len(_REQUEST_TIMESTAMPS) >= MAX_REQUESTS_PER_HOUR:
        wait = 3600 - (now - _REQUEST_TIMESTAMPS[0])
        raise RuntimeError(
            f"N2YO rate limit reached. Try again in {int(wait)}s."
        )
    _REQUEST_TIMESTAMPS.append(now)


def _get(endpoint: str, params: Optional[dict] = None) -> dict:
    """
    Generic authenticated GET against the N2YO REST API.
    Appends the API key automatically and handles HTTP errors.
    """
    _check_rate_limit()
    url = f"{config.N2YO_BASE_URL}/{endpoint}"
    payload = params or {}
    payload["apiKey"] = config.N2YO_API_KEY

    try:
        resp = requests.get(url, params=payload, timeout=15)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        logger.error("N2YO request timed out: %s", url)
        raise
    except requests.exceptions.HTTPError as exc:
        logger.error("HTTP error %s from N2YO: %s", exc.response.status_code, url)
        raise

    data = resp.json()
    logger.debug("N2YO response: %s", data)
    return data


# ── Public fetcher functions ──────────────────────────────────────────────────

def fetch_tle(norad_id: int) -> TLEData:
    """
    Fetch Two-Line Element set for a satellite.
    Endpoint: /tle/{id}
    """
    data = _get(f"tle/{norad_id}")
    info = data.get("info", {})
    tle_raw = data.get("tle", "")
    lines = [l.strip() for l in tle_raw.split("\r\n") if l.strip()]

    if len(lines) < 2:
        raise ValueError(f"Malformed TLE response for NORAD {norad_id}: {tle_raw!r}")

    return TLEData(
        norad_id=norad_id,
        name=info.get("satname", f"SAT-{norad_id}"),
        line1=lines[0],
        line2=lines[1],
    )


def fetch_positions(
    norad_id: int,
    observer_lat: float,
    observer_lon: float,
    observer_alt: float,
    seconds: int = config.POSITION_SECONDS,
) -> List[SatellitePosition]:
    """
    Fetch real-time position data for `seconds` seconds in one call.
    Endpoint: /positions/{id}/{lat}/{lon}/{alt}/{seconds}
    Batching avoids hammering the API.
    """
    seconds = min(seconds, 300)   # N2YO caps at 300 s per call
    data = _get(
        f"positions/{norad_id}/{observer_lat}/{observer_lon}/{observer_alt}/{seconds}"
    )
    info = data.get("info", {})
    name = info.get("satname", f"SAT-{norad_id}")
    positions: List[SatellitePosition] = []

    for p in data.get("positions", []):
        positions.append(
            SatellitePosition(
                norad_id=norad_id,
                name=name,
                timestamp=p["timestamp"],
                lat=p["satlatitude"],
                lon=p["satlongitude"],
                alt_km=p["sataltitude"],
                azimuth=p["azimuth"],
                elevation=p["elevation"],
                ra=p["ra"],
                dec=p["dec"],
                velocity_km_s=p.get("velocity", 0.0),
            )
        )

    logger.info("Fetched %d position snapshots for %s", len(positions), name)
    return positions


def fetch_passes(
    norad_id: int,
    observer_lat: float,
    observer_lon: float,
    observer_alt: float,
    days: int = config.PASS_DAYS,
    min_elevation: int = config.MIN_ELEVATION,
) -> List[PassEvent]:
    """
    Fetch upcoming passes above min_elevation for the next `days` days.
    Endpoint: /radiopasses/{id}/{lat}/{lon}/{alt}/{days}/{minEl}
    """
    data = _get(
        f"radiopasses/{norad_id}/{observer_lat}/{observer_lon}/"
        f"{observer_alt}/{days}/{min_elevation}"
    )
    info = data.get("info", {})
    name = info.get("satname", f"SAT-{norad_id}")
    passes: List[PassEvent] = []

    for p in data.get("passes", []):
        passes.append(
            PassEvent(
                norad_id=norad_id,
                name=name,
                aos_timestamp=p["startUTC"],
                los_timestamp=p["endUTC"],
                max_elevation=p["maxEl"],
                duration_s=p["endUTC"] - p["startUTC"], 
            )
        )

    logger.info("Fetched %d upcoming passes for %s", len(passes), name)
    return passes


def find_satellites_above(
    observer_lat: float,
    observer_lon: float,
    observer_alt: float,
    search_radius: int = 70,
    category: int = 0,
) -> list:
    """
    Use the /above endpoint to discover satellites currently overhead.
    Returns the raw list of satellite dicts.
    category=0 means all categories.
    """
    data = _get(
        f"above/{observer_lat}/{observer_lon}/{observer_alt}/"
        f"{search_radius}/{category}"
    )
    sats = data.get("above", [])
    logger.info("Found %d satellites above the observer", len(sats))
    return sats
