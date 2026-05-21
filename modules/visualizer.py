"""
modules/visualizer.py
----------------------
Phase 4 — Visualization & Dashboard.
Provides three views:
  1. World map with satellite ground track
  2. Polar radar (Az/El) plot
  3. Real-time console loop
"""

import math
import time
import datetime
import logging
from typing import List, Optional

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.animation import FuncAnimation
import matplotlib.ticker as mticker

import config
from modules.models import SatellitePosition, PassEvent, RFAnalysis, GroundStation
from modules.processor import (
    seconds_to_aos,
    seconds_to_los,
    is_pass_active,
    communication_window,
    slant_range_km,
)

logger = logging.getLogger(__name__)

# ── Colour palette ────────────────────────────────────────────────────────────
DARK_BG      = "#0d1117"
ACCENT_CYAN  = "#00e5ff"
ACCENT_AMBER = "#ffb300"
ACCENT_GREEN = "#00e676"
ACCENT_RED   = "#ff1744"
GRID_COLOR   = "#1e2a38"
TEXT_COLOR   = "#cdd9e5"


def _apply_dark_style() -> None:
    plt.style.use("dark_background")
    plt.rcParams.update({
        "figure.facecolor": DARK_BG,
        "axes.facecolor": DARK_BG,
        "axes.edgecolor": GRID_COLOR,
        "axes.labelcolor": TEXT_COLOR,
        "xtick.color": TEXT_COLOR,
        "ytick.color": TEXT_COLOR,
        "grid.color": GRID_COLOR,
        "text.color": TEXT_COLOR,
        "font.family": "monospace",
    })


# ────────────────────────────────────────────────────────────────────────────
# 1. WORLD MAP — Ground Track
# ────────────────────────────────────────────────────────────────────────────

def plot_ground_track(
    positions: List[SatellitePosition],
    ground: GroundStation,
    title: str = "Satellite Ground Track",
    live_positions: Optional[List[SatellitePosition]] = None,
) -> plt.Figure:
    """
    Draw the satellite's latitude/longitude path on a world map.
    Detects anti-meridian crossings and breaks the line accordingly.
    If live_positions is provided, draws them as a separate colour
    on top of the initial fetched track — showing the full session path.
    """
    _apply_dark_style()
    fig, ax = plt.subplots(figsize=(16, 8))
    fig.patch.set_facecolor(DARK_BG)
    ax.set_facecolor("#080f18")

    # Simple geographic background
    ax.set_xlim(-180, 180)
    ax.set_ylim(-90, 90)
    ax.set_xlabel("Longitude (°)")
    ax.set_ylabel("Latitude (°)")
    ax.set_title(title, color=ACCENT_CYAN, fontsize=14, pad=12)
    ax.grid(True, linestyle="--", linewidth=0.4, color=GRID_COLOR)

    # Draw equator and prime meridian
    ax.axhline(0, color=GRID_COLOR, linewidth=0.8)
    ax.axvline(0, color=GRID_COLOR, linewidth=0.8)

    # Latitude parallels
    for lat in range(-60, 90, 30):
        ax.axhline(lat, color=GRID_COLOR, linewidth=0.3, linestyle=":")

    def _draw_track(pos_list, color, alpha=0.85):
        """Draw a track segment, splitting at anti-meridian crossings."""
        lats = [p.lat for p in pos_list]
        lons = [p.lon for p in pos_list]
        segments_lat, segments_lon = [[]], [[]]
        for i in range(len(lons)):
            if i > 0 and abs(lons[i] - lons[i - 1]) > 180:
                segments_lat.append([])
                segments_lon.append([])
            segments_lat[-1].append(lats[i])
            segments_lon[-1].append(lons[i])
        for seg_lat, seg_lon in zip(segments_lat, segments_lon):
            ax.plot(seg_lon, seg_lat, color=color, linewidth=1.5, alpha=alpha)
        return lats, lons

    # Draw initial fetched track in cyan
    lats, lons = _draw_track(positions, ACCENT_CYAN)

    # Draw live accumulated track in amber (brighter, on top)
    if live_positions:
        live_lats, live_lons = _draw_track(live_positions, ACCENT_AMBER, alpha=0.95)
        # Mark session start and current live position
        ax.scatter(lons[0], lats[0], color=ACCENT_GREEN, s=80, zorder=5,
                   label="Session Start", marker="o")
        ax.scatter(live_lons[-1], live_lats[-1], color=ACCENT_AMBER, s=100, zorder=6,
                   label="Current Position", marker="D")
    else:
        # No live data yet — just mark start/end of fetched track
        if positions:
            ax.scatter(lons[0], lats[0], color=ACCENT_GREEN, s=80, zorder=5,
                       label="Track Start", marker="o")
            ax.scatter(lons[-1], lats[-1], color=ACCENT_RED, s=80, zorder=5,
                       label="Latest Position", marker="D")

    # Ground station marker
    ax.scatter(ground.lon, ground.lat, color=ACCENT_RED, s=120, zorder=7,
               marker="^", label=f"Ground Station ({ground.name})")
    ax.annotate(
        ground.name,
        (ground.lon, ground.lat),
        textcoords="offset points", xytext=(6, 6),
        fontsize=7, color=ACCENT_RED,
    )

    ax.legend(loc="lower left", fontsize=8,
              facecolor="#1a2332", edgecolor=GRID_COLOR)

    fig.tight_layout()
    return fig


# ────────────────────────────────────────────────────────────────────────────
# 2. POLAR RADAR — Azimuth / Elevation
# ────────────────────────────────────────────────────────────────────────────

def plot_radar(
    positions: List[SatellitePosition],
    title: str = "Sky Radar (Az/El)",
) -> plt.Figure:
    """
    Polar plot of the satellite's path through the local sky.
    Azimuth = angle (0° = North, clockwise).
    Elevation = distance from edge (90° = zenith at centre).
    """
    _apply_dark_style()
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"projection": "polar"})
    fig.patch.set_facecolor(DARK_BG)
    ax.set_facecolor("#080f18")

    # Polar: theta=azimuth (radians), r=90-elevation
    az_rad = [math.radians(p.azimuth) for p in positions]
    r_vals = [90 - p.elevation for p in positions]  # invert so zenith = centre

    # Colour by elevation (brighter = higher)
    elevations = [p.elevation for p in positions]
    norm_el = np.array(elevations)
    norm_el = (norm_el - norm_el.min()) / (norm_el.max() - norm_el.min() + 1e-9)

    scatter = ax.scatter(
        az_rad, r_vals,
        c=norm_el, cmap="cool",
        s=12, alpha=0.9, zorder=3,
    )

    # Draw track line
    ax.plot(az_rad, r_vals, color=ACCENT_CYAN, linewidth=1.2, alpha=0.6)

    # AOS / LOS markers
    if positions:
        ax.scatter(az_rad[0], r_vals[0], color=ACCENT_GREEN, s=100,
                   zorder=5, label="AOS")
        ax.scatter(az_rad[-1], r_vals[-1], color=ACCENT_RED, s=100,
                   zorder=5, label="LOS")

    # Elevation rings
    ax.set_ylim(0, 90)
    ax.set_yticks([0, 30, 60, 90])
    ax.set_yticklabels(["90°", "60°", "30°", "0°"], fontsize=7,
                        color=TEXT_COLOR)
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)    # clockwise = real-world compass
    ax.set_xticks(np.radians([0, 45, 90, 135, 180, 225, 270, 315]))
    ax.set_xticklabels(["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
                        color=TEXT_COLOR, fontsize=9)
    ax.grid(color=GRID_COLOR, linestyle="--", linewidth=0.5)
    ax.set_title(title, color=ACCENT_CYAN, fontsize=13, pad=18)
    ax.legend(loc="lower right", fontsize=8,
              facecolor="#1a2332", edgecolor=GRID_COLOR)

    plt.colorbar(scatter, ax=ax, label="Normalized Elevation",
                 shrink=0.6, pad=0.08)
    fig.tight_layout()
    return fig


# ────────────────────────────────────────────────────────────────────────────
# 3. REAL-TIME CONSOLE LOOP
# ────────────────────────────────────────────────────────────────────────────

def _fmt_duration(seconds: int) -> str:
    if seconds < 0:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _fmt_freq(freq_hz: float) -> str:
    return f"{freq_hz / 1e6:.4f} MHz"


def _bar(value: float, max_val: float, width: int = 20) -> str:
    filled = int(width * min(value, max_val) / max_val)
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def realtime_console(
    positions: List[SatellitePosition],
    rf_analyses: List[RFAnalysis],
    passes: List[PassEvent],
    ground: Optional[GroundStation] = None,
    refresh_s: int = config.REFRESH_INTERVAL,
    track_save_path: str = "assets/ground_track.png",
    track_save_interval: int = 10,
    satellite_name: str = "Satellite",
    refetch_callback=None,
) -> None:
    """
    Phase 4.3 — Real-time console dashboard with auto re-fetch.

    Iterates through pre-fetched position snapshots at `refresh_s` cadence.
    When the current batch is exhausted, calls `refetch_callback()` to get
    a fresh batch — enabling continuous indefinite tracking.

    refetch_callback: callable() → (List[SatellitePosition], List[RFAnalysis])
                      Returns new positions and their RF analyses.
                      If None, stops after the initial batch.

    The ground track image is updated every `track_save_interval` snapshots,
    showing the full accumulated live path in amber over the initial cyan track.
    Press Ctrl+C to stop.
    """
    if not positions:
        print("No position data to display.")
        return

    print(f"\n{'═' * 62}")
    print(f"  🛰  SATELLITE TRACKER CONSOLE  — Press Ctrl+C to exit")
    print(f"{'═' * 62}")

    next_pass = communication_window(passes)

    # Initial batch stored separately (cyan track)
    initial_positions = list(positions)

    # Accumulate ALL positions shown during the session (amber track)
    live_positions: List[SatellitePosition] = []

    # Working batch — starts with the initial fetch, replaced on re-fetch
    current_positions = list(positions)
    current_rf = list(rf_analyses)
    total_snapshots = 0

    try:
        while True:
            batch_exhausted = True

            for idx, (pos, rf) in enumerate(zip(current_positions, current_rf)):
                batch_exhausted = False
                live_positions.append(pos)
                total_snapshots += 1

                ts = datetime.datetime.utcfromtimestamp(pos.timestamp).strftime(
                    "%Y-%m-%d %H:%M:%S UTC"
                )

                # AOS/LOS countdown
                if next_pass:
                    if is_pass_active(next_pass):
                        window_str = (
                            f"🟢 IN WINDOW — LOS in {_fmt_duration(seconds_to_los(next_pass))}"
                        )
                    else:
                        window_str = (
                            f"🔵 Next pass in {_fmt_duration(seconds_to_aos(next_pass))} "
                            f"(max el: {next_pass.max_elevation:.1f}°)"
                        )
                else:
                    window_str = "⚫ No upcoming passes found"

                # Compute real velocity from slant range change
                if len(live_positions) < 2 or ground is None:
                    display_velocity = 0.0
                else:
                    prev = live_positions[-2]
                    slant_now = slant_range_km(
                        ground.lat, ground.lon, ground.alt_m,
                        pos.lat, pos.lon, pos.alt_km,
                    )
                    slant_prev = slant_range_km(
                        ground.lat, ground.lon, ground.alt_m,
                        prev.lat, prev.lon, prev.alt_km,
                    )
                    dt = pos.timestamp - prev.timestamp
                    display_velocity = abs((slant_now - slant_prev) / dt) if dt > 0 else 0.0

                shift_sign = "+" if rf.doppler_shift_hz >= 0 else ""
                quality_icon = {
                    "Excellent": "🟢",
                    "Good":      "🟡",
                    "Marginal":  "🟠",
                    "No Signal": "🔴",
                }.get(rf.signal_quality, "⚪")

                print(
                    f"\r\033[K"
                    f"\n{'─' * 62}\n"
                    f"  Satellite : {pos.name:<20}  [{ts}]\n"
                    f"  Position  : Lat {pos.lat:+08.4f}°  Lon {pos.lon:+09.4f}°  "
                    f"Alt {pos.alt_km:.1f} km\n"
                    f"  Sky       : Az {pos.azimuth:6.2f}°   El {pos.elevation:+6.2f}°\n"
                    f"  Velocity  : {display_velocity:.3f} km/s\n"
                    f"  Slant Rng : {rf.slant_range_km:,.1f} km\n"
                    f"  Doppler   : {shift_sign}{rf.doppler_shift_hz:+,.1f} Hz  "
                    f"→  {_fmt_freq(rf.shifted_freq_hz)}\n"
                    f"  FSPL      : {rf.fspl_db:.2f} dB  "
                    f"{_bar(rf.fspl_db, 160)}\n"
                    f"  Signal    : {quality_icon} {rf.signal_quality}\n"
                    f"  Comm Win  : {window_str}\n"
                    f"  Tracked   : {total_snapshots} snapshots | "
                    f"Live path: {len(live_positions)} pts\n"
                    f"{'─' * 62}",
                    end="", flush=True,
                )

                # Save updated ground track every N snapshots
                if ground is not None and total_snapshots % track_save_interval == 0:
                    try:
                        fig = plot_ground_track(
                            initial_positions,
                            ground,
                            title=f"{satellite_name} — Full Session Ground Track",
                            live_positions=live_positions,
                        )
                        fig.savefig(
                            track_save_path, dpi=150,
                            bbox_inches="tight",
                            facecolor=fig.get_facecolor(),
                        )
                        plt.close(fig)
                        print(
                            f"\n  🗺  Ground track updated — "
                            f"{len(live_positions)} positions tracked",
                            flush=True,
                        )
                    except Exception as e:
                        logger.warning("Failed to save live ground track: %s", e)

                time.sleep(refresh_s)

            # Batch exhausted — try re-fetch
            if refetch_callback is not None:
                print(f"\n\n  🔄 Batch complete. Fetching new positions...", flush=True)
                try:
                    prev_pos = live_positions[-1] if live_positions else None
                    new_positions, new_rf = refetch_callback(prev_pos)
                    if new_positions:
                        current_positions = new_positions
                        current_rf = new_rf
                        print(
                            f"  ✔ {len(new_positions)} new snapshots loaded. Continuing...\n",
                            flush=True,
                        )
                    else:
                        print("  ⚠ No new positions received. Stopping.", flush=True)
                        break
                except Exception as e:
                    print(f"  ❌ Re-fetch failed: {e}. Stopping.", flush=True)
                    break
            else:
                break  # No callback — stop after initial batch

    except KeyboardInterrupt:
        pass

    # Save final ground track on exit
    if ground is not None and live_positions:
        try:
            fig = plot_ground_track(
                initial_positions,
                ground,
                title=f"{satellite_name} — Full Session Ground Track",
                live_positions=live_positions,
            )
            fig.savefig(
                track_save_path, dpi=150,
                bbox_inches="tight",
                facecolor=fig.get_facecolor(),
            )
            plt.close(fig)
            print(f"\n\n  🗺  Final ground track saved → {track_save_path}")
            print(f"       Total positions tracked: {len(live_positions)}\n")
        except Exception as e:
            logger.warning("Failed to save final ground track: %s", e)


# ────────────────────────────────────────────────────────────────────────────
# 4. SAVE FIGURES HELPER
# ────────────────────────────────────────────────────────────────────────────

def save_figure(fig: plt.Figure, path: str) -> None:
    """Save a matplotlib figure to disk at high DPI."""
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    logger.info("Figure saved → %s", path)
    print(f"  ✔ Figure saved → {path}")
