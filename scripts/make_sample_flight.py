"""Generate a synthetic but realistic drone flight telemetry log.

Deterministic (no randomness), so the committed CSV is stable and the pipeline
is reproducible.

    python scripts/make_sample_flight.py > data/sample_flight.csv
"""

from __future__ import annotations

import csv
import math
import sys

BASE_LAT = -43.5321  # near Christchurch, New Zealand
BASE_LON = 172.6362
M_PER_DEG_LAT = 111_320.0


def m_to_dlat(metres: float) -> float:
    return metres / M_PER_DEG_LAT


def m_to_dlon(metres: float, lat: float) -> float:
    return metres / (M_PER_DEG_LAT * math.cos(math.radians(lat)))


def main() -> None:
    rows: list[tuple] = []
    time_s = 0
    battery_v = 16.8  # full 4S LiPo

    def add(east_m: float, north_m: float, alt_m: float, speed_ms: float) -> None:
        nonlocal time_s, battery_v
        lat = BASE_LAT + m_to_dlat(north_m)
        lon = BASE_LON + m_to_dlon(east_m, BASE_LAT)
        rows.append((time_s, lat, lon, alt_m, battery_v, speed_ms))
        time_s += 1
        battery_v = max(14.0, battery_v - 0.012)  # gentle discharge

    # 1) Vertical climb to 80 m over 20 s, with a little drift.
    for i in range(20):
        add(east_m=0.5 * i, north_m=0.0, alt_m=4.0 * i, speed_ms=1.0 if i < 2 else 2.0)

    # 2) Lawnmower survey pattern at 80 m: east-west passes, stepping north.
    east, north, alt = 10.0, 0.0, 80.0
    pass_len, step = 120.0, 25.0
    direction = 1
    for _pass in range(6):
        for _ in range(int(pass_len / 6)):
            east += direction * 6.0
            add(east_m=east, north_m=north, alt_m=alt, speed_ms=6.0)
        for _ in range(4):
            north += step / 4
            add(east_m=east, north_m=north, alt_m=alt, speed_ms=4.0)
        direction *= -1

    # 3) Return toward base and descend over 25 s.
    start_e, start_n = east, north
    for i in range(25):
        f = i / 24
        add(east_m=start_e * (1 - f), north_m=start_n * (1 - f),
            alt_m=80.0 * (1 - f), speed_ms=5.0 * (1 - f) + 1.0)

    # 4) Touchdown.
    add(east_m=0.0, north_m=0.0, alt_m=0.0, speed_ms=0.0)

    writer = csv.writer(sys.stdout)
    writer.writerow(["time_s", "lat", "lon", "alt_m", "battery_v", "speed_ms"])
    for t, lat, lon, alt, batt, spd in rows:
        writer.writerow([t, f"{lat:.6f}", f"{lon:.6f}", f"{alt:.1f}", f"{batt:.2f}", f"{spd:.1f}"])


if __name__ == "__main__":
    main()
