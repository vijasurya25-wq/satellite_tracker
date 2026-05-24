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

from flask import Flask, Response, render_template, jsonify

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

GROUND = GroundStation(
    lat=config.GROUND_LAT,
    lon=config.GROUND_LON,
    alt_m=config.GROUND_ALT,
    name="Ground Station",
)


# ── Background fetch loop ─────────────────────────────────────────────────────

def _fetch_loop():
    """Runs in a daemon thread. Fetches new positions every REFRESH_INTERVAL seconds."""
    global _passes, _ground_track, _latest

    prev_position = None
    passes_last_fetched = 0

    logger.info("Background fetch loop started for NORAD %d", config.NORAD_ID)

    while True:
        try:
            # Re-fetch passes every 5 minutes
            now = time.time()
            if now - passes_last_fetched > 300:
                fetched = fetch_passes(
                    config.NORAD_ID,
                    GROUND.lat, GROUND.lon, GROUND.alt_m,
                )
                with _state_lock:
                    _passes = fetched
                passes_last_fetched = now
                logger.info("Refreshed %d upcoming passes", len(fetched))

            positions = fetch_positions(
                config.NORAD_ID,
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
            pos = positions[-1]
            rf  = rf_results[-1]

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

            snapshot = {
                "timestamp": pos.timestamp,
                "timestamp_local": utc_to_local(pos.timestamp),
                "name": pos.name,
                "lat": round(pos.lat, 4),
                "lon": round(pos.lon, 4),
                "alt_km": round(pos.alt_km, 1),
                "azimuth": round(pos.azimuth, 1),
                "elevation": round(pos.elevation, 1),
                "velocity_km_s": round(pos.velocity_km_s, 3),
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
            }

            with _state_lock:
                _latest = snapshot
                _ground_track.append([pos.lat, pos.lon])
                if len(_ground_track) > 300:
                    _ground_track = _ground_track[-300:]

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
        sat_name=f"NORAD {config.NORAD_ID}",
        ground_lat=GROUND.lat,
        ground_lon=GROUND.lon,
        carrier_freq=config.CARRIER_FREQ_HZ / 1e6,
    )


@app.route("/stream")
def stream():
    """SSE endpoint — browser connects once and receives events forever."""
    def generate():
        last_ts = 0
        yield ": connected\n\n"          # flush the buffer immediately on connect

        while True:
            with _state_lock:
                snap = dict(_latest)
                track = list(_ground_track)

            if snap and snap.get("timestamp", 0) != last_ts:
                last_ts = snap["timestamp"]
                snap["ground_track"] = track
                yield f"data: {json.dumps(snap)}\n\n"
            else:
                yield ": keepalive\n\n"  # comment line — ignored by browser but forces flush

            time.sleep(1)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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
    return jsonify(data)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    validate_config()

    # Start background fetch thread
    t = threading.Thread(target=_fetch_loop, daemon=True)
    t.start()

    print("\n  Satellite Tracker — Web Dashboard")
    print(f"  Tracking NORAD {config.NORAD_ID}")
    print(f"  Observer: {GROUND.lat}°, {GROUND.lon}°")
    print(f"  Open your browser at:  http://localhost:5000\n")

    app.run(host="0.0.0.0", port=5000, threaded=True, debug=False)
