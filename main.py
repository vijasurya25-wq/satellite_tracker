"""
main.py
-------
Entry point for the Real-Time Satellite Tracker.
Run:  python main.py
"""

import os
import sys

# ── Bootstrap ─────────────────────────────────────────────────────────────────
from utils.logger import setup_logging
setup_logging("INFO")

from utils.validators import validate_config
try:
    validate_config()
except ValueError as e:
    print(f"\n❌  {e}\n")
    sys.exit(1)

import config
from modules.models import GroundStation, TrackSession
from modules.collector import fetch_tle, fetch_positions, fetch_passes
from modules.processor import analyse_track, analyse_track_append, communication_window, positions_to_arrays
from modules.visualizer import (
    plot_ground_track,
    plot_radar,
    realtime_console,
    save_figure,
)
from utils.time_utils import utc_to_local, duration_str
import time


def main():
    print("\n" + "═" * 62)
    print("  🛰  Real-Time Satellite Tracker & Communication Predictor")
    print("═" * 62)

    # ── Ground station ────────────────────────────────────────────────────────
    ground = GroundStation(
        lat=config.GROUND_LAT,
        lon=config.GROUND_LON,
        alt_m=config.GROUND_ALT,
        name="My Ground Station",
    )
    print(f"\n📍 Ground Station: ({ground.lat}, {ground.lon}, {ground.alt_m}m)")

    session = TrackSession(ground_station=ground)

    # ── Phase 2: Fetch data ───────────────────────────────────────────────────
    print(f"\n⬇  Fetching TLE for NORAD {config.NORAD_ID}...")
    session.tle = fetch_tle(config.NORAD_ID)
    print(f"   ✔ {session.tle.name}")

    print(f"\n⬇  Fetching {config.POSITION_SECONDS}s of position data (batched)...")
    session.positions = fetch_positions(
        config.NORAD_ID,
        ground.lat, ground.lon, ground.alt_m,
        seconds=config.POSITION_SECONDS,
    )
    print(f"   ✔ {len(session.positions)} position snapshots received")

    print(f"\n⬇  Fetching upcoming passes ({config.PASS_DAYS} days ahead)...")
    session.passes = fetch_passes(
        config.NORAD_ID,
        ground.lat, ground.lon, ground.alt_m,
        days=config.PASS_DAYS,
        min_elevation=config.MIN_ELEVATION,
    )
    print(f"   ✔ {len(session.passes)} passes found")

    # ── Phase 3: ECE analysis ─────────────────────────────────────────────────
    print("\n⚙  Running ECE Math Engine...")
    session.rf_analyses = analyse_track(
        session.positions, ground, config.CARRIER_FREQ_HZ
    )
    print(f"   ✔ RF analysis complete for {len(session.rf_analyses)} snapshots")

    # Print next pass summary
    next_pass = communication_window(session.passes)
    if next_pass:
        aos_local = utc_to_local(next_pass.aos_timestamp)
        los_local = utc_to_local(next_pass.los_timestamp)
        print(f"\n🔭 Next Communication Window:")
        print(f"   AOS : {aos_local}")
        print(f"   LOS : {los_local}")
        print(f"   Max Elevation : {next_pass.max_elevation:.1f}°")
        print(f"   Duration      : {duration_str(next_pass.duration_s)}")
    else:
        print("\n⚫ No upcoming passes in the configured window.")

    # ── Phase 4: Visualizations ───────────────────────────────────────────────
    os.makedirs("assets", exist_ok=True)

    print("\n🗺  Rendering ground track map...")
    fig_map = plot_ground_track(
        session.positions, ground,
        title=f"{session.tle.name} — Ground Track",
    )
    save_figure(fig_map, "assets/ground_track.png")

    print("🎯 Rendering radar view...")
    fig_radar = plot_radar(
        session.positions,
        title=f"{session.tle.name} — Sky Radar",
    )
    save_figure(fig_radar, "assets/radar.png")

    # ── Phase 4.3: Live console with auto re-fetch ────────────────────────────
    print("\n📡 Starting real-time console (Ctrl+C to stop)...\n")
    time.sleep(1)

    def refetch_callback(prev_position):
        """Fetch a fresh batch of positions and analyse them."""
        print("\n  ⬇  Re-fetching position data...", flush=True)
        new_positions = fetch_positions(
            config.NORAD_ID,
            ground.lat, ground.lon, ground.alt_m,
            seconds=config.POSITION_SECONDS,
        )
        new_rf = analyse_track_append(
            new_positions, ground, config.CARRIER_FREQ_HZ,
            prev_position=prev_position,
        )
        return new_positions, new_rf

    realtime_console(
        session.positions,
        session.rf_analyses,
        session.passes,
        ground=ground,
        refresh_s=config.REFRESH_INTERVAL,
        track_save_path="assets/ground_track.png",
        track_save_interval=10,
        satellite_name=session.tle.name,
        refetch_callback=refetch_callback,
    )

    print("\n✅ Session complete. Plots saved to assets/\n")


if __name__ == "__main__":
    main()
