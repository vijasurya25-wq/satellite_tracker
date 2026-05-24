"""
utils/geocoder.py
-----------------
Reverse geocoding: lat/lon -> human-readable location name.

Strategy:
  1. reverse_geocoder (offline, GeoNames data) for land points
  2. GeoNames ocean REST API for open water
  3. Coordinate string as last resort if both fail

Register free at geonames.org and set GEONAMES_USERNAME in .env
for production. Falls back to 'demo' (rate-limited) for testing.
"""

import logging
import requests
import reverse_geocoder as rg
from functools import lru_cache
from geopy.distance import geodesic
import config
import pycountry

logger = logging.getLogger(__name__)

# How close (km) a result must be to count as "on land"
_LAND_THRESHOLD_KM = 150

def _country_name(cc: str) -> str:
    try:
        return pycountry.countries.get(alpha_2=cc).name
    except Exception:
        return cc
    
def get_location_name(lat: float, lon: float) -> str:
    """
    Public API. Returns a landmark/region/ocean name for any lat/lon.
    Safe to call on every position update — results are cached.
    """
    grid = _grid_key(lat, lon)
    return _cached_location(*grid)


def _grid_key(lat: float, lon: float, precision: float = 0.5):
    return (round(lat / precision) * precision,
            round(lon / precision) * precision)


@lru_cache(maxsize=1024)
def _cached_location(grid_lat: float, grid_lon: float) -> str:
    # ── Step 1: try offline land lookup ──────────────────────────────────────
    try:
        results = rg.search((grid_lat, grid_lon), mode=1, verbose=False)
        if results:
            r = results[0]
            result_coords = (float(r["lat"]), float(r["lon"]))
            dist_km = geodesic((grid_lat, grid_lon), result_coords).km
            if dist_km < _LAND_THRESHOLD_KM:
                name = r.get("name", "")
                country = r.get("cc", "")
                admin = r.get("admin1", "")
                if name and country:
                    full_country = _country_name(country)
                    label = f"{admin}, {full_country}" if admin else f"{name}, {full_country}"
                    return label
    except Exception as exc:
        logger.debug("reverse_geocoder error: %s", exc)

    # ── Step 2: GeoNames ocean API for open water ─────────────────────────────
    return _ocean_name(grid_lat, grid_lon)


@lru_cache(maxsize=512)
def _ocean_name(lat: float, lon: float) -> str:
    username = getattr(config, "GEONAMES_USERNAME", "demo")
    try:
        resp = requests.get(
            "http://api.geonames.org/oceanJSON",
            params={"lat": lat, "lng": lon, "username": username},
            timeout=5,
        )
        data = resp.json()
        if "ocean" in data:
            return data["ocean"]["name"]
        # GeoNames may return a status error (e.g. over quota)
        if "status" in data:
            logger.warning("GeoNames status: %s", data["status"].get("message"))
    except Exception as exc:
        logger.debug("GeoNames ocean error: %s", exc)

    # ── Step 3: bare coordinate fallback ─────────────────────────────────────
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"{abs(lat):.1f}°{ns}, {abs(lon):.1f}°{ew}"
