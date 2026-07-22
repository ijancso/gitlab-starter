"""
Ingest a telemetry CSV into PostGIS.

Idempotent: running twice on the same file is safe.
The deduplication key is the source_file path stored in the flights table.
If that row already exists, the insert is skipped and we exit early — no
duplicate track_points can appear because they are only inserted in the same
transaction that creates the flights row.
"""

import csv
import os
import sys
from pathlib import Path

import psycopg


def ingest(csv_path: str, database_url: str) -> int:
    """Insert a flight CSV into the DB. Returns the flight id (new or existing)."""
    source_file = str(Path(csv_path).resolve())

    with psycopg.connect(database_url) as conn:
        # Apply schema (idempotent: CREATE ... IF NOT EXISTS throughout).
        schema_sql = (Path(__file__).parent / "schema.sql").read_text()
        conn.execute(schema_sql)

        # Attempt to insert a flights row. ON CONFLICT DO NOTHING means a
        # second run with the same file simply skips the insert without error.
        row = conn.execute(
            """
            INSERT INTO flights (source_file)
            VALUES (%s)
            ON CONFLICT (source_file) DO NOTHING
            RETURNING id
            """,
            (source_file,),
        ).fetchone()

        if row is None:
            # Flight already ingested; look up its id and return.
            existing = conn.execute(
                "SELECT id FROM flights WHERE source_file = %s", (source_file,)
            ).fetchone()
            print(f"Already ingested: {source_file} (flight_id={existing[0]})")
            conn.commit()
            return existing[0]

        flight_id = row[0]

        # Read CSV and build track_points rows.
        # ST_MakePoint(lon, lat, alt) — note lon before lat, matching GeoJSON / WKT convention.
        # PostGIS stores X=longitude, Y=latitude, Z=altitude.
        with open(csv_path, newline="") as fh:
            reader = csv.DictReader(fh)
            rows = [
                (
                    flight_id,
                    float(r["time_s"]),
                    float(r["alt_m"]),
                    float(r["battery_v"]),
                    float(r["speed_ms"]),
                    float(r["lon"]),
                    float(r["lat"]),
                    float(r["alt_m"]),
                )
                for r in reader
            ]

        conn.executemany(
            """
            INSERT INTO track_points (flight_id, time_s, altitude, battery_v, speed_ms, geom)
            VALUES (
                %s, %s, %s, %s, %s,
                ST_SetSRID(ST_MakePoint(%s, %s, %s), 4326)
            )
            """,
            rows,
        )

        conn.commit()
        print(f"Ingested {len(rows)} track points for flight_id={flight_id}")
        return flight_id


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m geo.ingest <path/to/flight.csv>")
        sys.exit(1)

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL environment variable is required")
        sys.exit(1)

    ingest(sys.argv[1], db_url)


if __name__ == "__main__":
    main()
