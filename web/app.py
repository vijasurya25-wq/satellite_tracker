"""
web/app.py
----------
Flask backend — serves the live dashboard and streams satellite
telemetry to the browser via Server-Sent Events (SSE).

Run:  python web/app.py
Then open:  http://localhost:5000
"""

import sys
import os
import json
import time
import logging
import threading
import math
from flask import Flask, Response, render_template, jsonify, request

# Allow imports from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from modules.collector import fetch_positions, fetch_passes, fetch_tle
from modules.processor import analyse_track_append, communication_window, seconds_to_aos, is_pass_active
from modules.models import GroundStation, TrackSession
from utils.validators import validate_config
from utils.logger import setup_logging
from utils.time_utils import utc_to_local, duration_str
from utils.geocoder import get_location_name

setup_logging("INFO")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ── Shared state (written by background thread, read by SSE clients) ──────────
_state_lock = threading.Lock()
_latest: dict = {}          # latest telemetry snapshot
_passes: list = []          # upcoming passes (refreshed every 5 min)
_ground_track: list = []    # list of [lat, lon] for the polyline (last 300 pts)
_elevation_history: list = []

# ── Runtime-changeable NORAD ID (default: ISS = 25544) ───────────────────────
_current_norad: int = config.NORAD_ID          # always starts as 25544 (ISS)
_norad_changed: bool = False                   # flag for fetch loop to reset

GROUND = GroundStation(
    lat=config.GROUND_LAT,
    lon=config.GROUND_LON,
    alt_m=config.GROUND_ALT,
    name="Ground Station",
)


# ── Background fetch loop ─────────────────────────────────────────────────────

def _fetch_loop():
    """Runs in a daemon thread. Fetches new positions every REFRESH_INTERVAL seconds."""
    global _passes, _ground_track, _latest, _elevation_history
    global _current_norad, _norad_changed

    prev_position = None
    passes_last_fetched = 0
    loop_norad = _current_norad

    logger.info("Background fetch loop started for NORAD %d", loop_norad)

    while True:
        try:
            # Detect NORAD change from dashboard — reset all history
            with _state_lock:
                if _norad_changed:
                    loop_norad = _current_norad
                    _norad_changed = False
                    _ground_track = []
                    _elevation_history = []
                    _latest = {}
                    passes_last_fetched = 0
                    prev_position = None
                    logger.info("NORAD ID changed — now tracking %d", loop_norad)

            # Re-fetch passes every 5 minutes
            now = time.time()
            if now - passes_last_fetched > 300:
                fetched = fetch_passes(
                    loop_norad,
                    GROUND.lat, GROUND.lon, GROUND.alt_m,
                )
                with _state_lock:
                    _passes = fetched
                passes_last_fetched = now
                logger.info("Refreshed %d upcoming passes", len(fetched))

            positions = fetch_positions(
                loop_norad,
                GROUND.lat, GROUND.lon, GROUND.alt_m,
                seconds=config.POSITION_SECONDS,
            )

            if not positions:
                time.sleep(config.REFRESH_INTERVAL)
                continue

            rf_results = analyse_track_append(
                positions, GROUND,
                carrier_freq_hz=config.CARRIER_FREQ_HZ,
                prev_position=prev_position,
            )
            prev_position = positions[-1]

            # Latest snapshot
            pos = positions[0]
            if len(positions) > 1:
                from modules.processor import analyse_position, slant_range_km as slant_fn
                slant_now  = slant_fn(GROUND.lat, GROUND.lon, GROUND.alt_m,
                                    positions[1].lat, positions[1].lon, positions[1].alt_km)
                slant_prev = slant_fn(GROUND.lat, GROUND.lon, GROUND.alt_m,
                                    positions[0].lat, positions[0].lon, positions[0].alt_km)
                dt = positions[1].timestamp - positions[0].timestamp
                radial_vel = (slant_now - slant_prev) / dt if dt > 0 else None
                rf = analyse_position(pos, GROUND, config.CARRIER_FREQ_HZ, radial_vel)
            else:
                rf = rf_results[0]

            # Reverse geocode (cached — fast after first hit)
            location_name = get_location_name(pos.lat, pos.lon)

            # Next pass info
            with _state_lock:
                next_pass = communication_window(_passes)

            if next_pass:
                if is_pass_active(next_pass):
                    pass_str = f"ACTIVE — LOS in {duration_str(next_pass.los_timestamp - int(time.time()))}"
                    pass_active = True
                else:
                    pass_str = f"in {duration_str(seconds_to_aos(next_pass))} (max {next_pass.max_elevation:.1f}°)"
                    pass_active = False
                pass_time_local = utc_to_local(next_pass.aos_timestamp)
            else:
                pass_str = "No passes in prediction window"
                pass_time_local = "—"
                pass_active = False

            radial_vel = abs(rf.doppler_shift_hz * config.SPEED_OF_LIGHT / config.CARRIER_FREQ_HZ) / 1000
            logger.info("DEBUG RF | doppler=%.1f Hz | radial_vel=%.3f km/s | slant=%.1f km",
                rf.doppler_shift_hz, radial_vel, rf.slant_range_km)

            GM = 3.986e14
            R_EARTH_M = 6.371e6
            r = (R_EARTH_M + pos.alt_km * 1000)
            orbital_speed_km_s = math.sqrt(GM / r) / 1000

            snapshot = {
                "timestamp": pos.timestamp,
                "timestamp_local": utc_to_local(pos.timestamp),
                "name": pos.name,
                "norad_id": loop_norad,
                "lat": round(pos.lat, 4),
                "lon": round(pos.lon, 4),
                "alt_km": round(pos.alt_km, 1),
                "azimuth": round(pos.azimuth, 1),
                "elevation": round(pos.elevation, 1),
                "velocity_km_s": round(orbital_speed_km_s, 3),
                "location_name": location_name,
                # RF
                "doppler_hz": round(rf.doppler_shift_hz, 1),
                "shifted_freq_mhz": round(rf.shifted_freq_hz / 1e6, 6),
                "fspl_db": round(rf.fspl_db, 2),
                "slant_range_km": round(rf.slant_range_km, 1),
                "signal_quality": rf.signal_quality,
                "is_readable": rf.is_readable,
                # Pass
                "next_pass": pass_str,
                "next_pass_time": pass_time_local,
                "pass_active": pass_active,
                # Ground track point for the map
                "track_point": [pos.lat, pos.lon],
                "received_power_dbm": rf.received_power_dbm,
                "link_margin_db":     rf.link_margin_db,
                "link_feasible":      rf.link_feasible,
            }

            with _state_lock:
                _latest = snapshot
                _ground_track.append([pos.lat, pos.lon])
                _elevation_history.append([pos.timestamp, pos.elevation])
                if len(_ground_track) > 300:
                    _ground_track = _ground_track[-300:]
                if len(_elevation_history) > 300:
                    _elevation_history = _elevation_history[-300:]

            logger.info(
                "%s | %.4f°, %.4f° | %s | %s",
                pos.name, pos.lat, pos.lon,
                location_name, rf.signal_quality,
            )

        except Exception as exc:
            logger.error("Fetch loop error: %s", exc, exc_info=True)

        time.sleep(config.REFRESH_INTERVAL)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html",
        sat_name=f"NORAD {_current_norad}",
        ground_lat=GROUND.lat,
        ground_lon=GROUND.lon,
        carrier_freq=config.CARRIER_FREQ_HZ / 1e6,
        tx_power=config.TX_POWER_DBM,
        rx_sensitivity=config.RX_SENSITIVITY_DBM,
        default_norad=_current_norad,
    )


@app.route("/api/set_norad", methods=["POST"])
def api_set_norad():
    """Change the tracked satellite at runtime without restarting."""
    global _current_norad, _norad_changed
    data = request.get_json(force=True, silent=True) or {}
    try:
        new_id = int(data.get("norad_id", 0))
        if new_id <= 0:
            return jsonify({"ok": False, "error": "Invalid NORAD ID"}), 400
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "NORAD ID must be an integer"}), 400

    with _state_lock:
        _current_norad = new_id
        _norad_changed = True

    logger.info("NORAD ID changed to %d via dashboard", new_id)
    return jsonify({"ok": True, "norad_id": new_id})


@app.route("/api/current_norad")
def api_current_norad():
    return jsonify({"norad_id": _current_norad})


@app.route("/api/passes")
def api_passes():
    with _state_lock:
        passes_data = [
            {
                "name": p.name,
                "aos": utc_to_local(p.aos_timestamp),
                "los": utc_to_local(p.los_timestamp),
                "max_elevation": p.max_elevation,
                "duration_s": p.duration_s,
                "active": is_pass_active(p),
            }
            for p in _passes
        ]
    return jsonify(passes_data)


@app.route("/api/status")
def api_status():
    with _state_lock:
        data = dict(_latest)
        data["ground_track"] = list(_ground_track)
        data["elevation_history"] = list(_elevation_history)
    return jsonify(data)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    validate_config()

    # Start background fetch thread
    t = threading.Thread(target=_fetch_loop, daemon=True)
    t.start()

    print("\n  Satellite Tracker — Web Dashboard")
    print(f"  Tracking NORAD {_current_norad} (ISS by default)")
    print(f"  Observer: {GROUND.lat}°, {GROUND.lon}°")
    print(f"  Open your browser at:  http://localhost:5000\n")

    app.run(host="0.0.0.0", port=5000, threaded=True, debug=False)
