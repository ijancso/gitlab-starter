"""Render a visual flight report (PNG) from telemetry samples.

This is the only module that needs matplotlib, so it is imported lazily by the
CLI. The backend is forced to "Agg" so it runs headless in CI.

The report has three panels:
  * the flight route, coloured by altitude, with takeoff/landing markers
  * altitude over time
  * battery voltage over time
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # headless: no display needed in CI

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402  (must come after backend selection)
from matplotlib.collections import LineCollection  # noqa: E402

from flightlog.metrics import FlightMetrics  # noqa: E402
from flightlog.telemetry import Sample  # noqa: E402


def _margin(low: float, high: float, frac: float = 0.08) -> float:
    span = high - low
    return span * frac if span else 0.0001


def render_report(samples: list[Sample], metrics: FlightMetrics, out_path: str) -> str:
    """Draw the flight report and save it to out_path. Returns out_path."""
    lons = [s.lon for s in samples]
    lats = [s.lat for s in samples]
    alts = [s.alt_m for s in samples]
    times = [s.time_s for s in samples]
    batts = [s.battery_v for s in samples]

    fig = plt.figure(figsize=(12, 6), dpi=120)
    grid = fig.add_gridspec(2, 2, width_ratios=[2.0, 1.4], hspace=0.35, wspace=0.25)

    # --- Route, coloured by altitude ---
    ax_route = fig.add_subplot(grid[:, 0])
    points = np.array([lons, lats]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    line = LineCollection(segments, cmap="viridis", linewidth=2.5)
    line.set_array(np.array(alts[:-1]))
    ax_route.add_collection(line)
    ax_route.scatter([lons[0]], [lats[0]], marker="o", s=110, color="#2e7d32",
                     edgecolor="white", zorder=5, label="Takeoff")
    ax_route.scatter([lons[-1]], [lats[-1]], marker="s", s=110, color="#c62828",
                     edgecolor="white", zorder=5, label="Landing")
    ax_route.set_xlim(min(lons) - _margin(min(lons), max(lons)),
                      max(lons) + _margin(min(lons), max(lons)))
    ax_route.set_ylim(min(lats) - _margin(min(lats), max(lats)),
                      max(lats) + _margin(min(lats), max(lats)))
    ax_route.set_aspect("equal", adjustable="datalim")
    ax_route.set_title("Flight route (colour = altitude)")
    ax_route.set_xlabel("Longitude")
    ax_route.set_ylabel("Latitude")
    ax_route.legend(loc="best")
    ax_route.grid(True, alpha=0.3)
    cbar = fig.colorbar(line, ax=ax_route, fraction=0.046, pad=0.04)
    cbar.set_label("Altitude (m)")

    # --- Altitude over time ---
    ax_alt = fig.add_subplot(grid[0, 1])
    ax_alt.plot(times, alts, color="#1e88e5")
    ax_alt.fill_between(times, alts, color="#1e88e5", alpha=0.15)
    ax_alt.set_title("Altitude over time")
    ax_alt.set_xlabel("Time (s)")
    ax_alt.set_ylabel("Altitude (m)")
    ax_alt.grid(True, alpha=0.3)

    # --- Battery over time ---
    ax_batt = fig.add_subplot(grid[1, 1])
    ax_batt.plot(times, batts, color="#8e24aa")
    ax_batt.set_title("Battery over time")
    ax_batt.set_xlabel("Time (s)")
    ax_batt.set_ylabel("Voltage (V)")
    ax_batt.grid(True, alpha=0.3)

    fig.suptitle(
        f"Flight report  -  {metrics.duration_s:.0f} s, "
        f"{metrics.distance_m:.0f} m travelled, "
        f"max alt {metrics.max_altitude_m:.0f} m, "
        f"min battery {metrics.min_battery_v:.1f} V",
        fontsize=13,
    )
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return out_path
