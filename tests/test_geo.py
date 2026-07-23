"""
Integration tests for the geospatial track service.

Requires a running PostGIS instance. Set DATABASE_URL to point at it, or the
whole module is skipped. The sample flight CSV is copied to a temp path for
each test session so the ingest deduplication key is unique and does not
collide with any manually-ingested data.

Run with:
    DATABASE_URL=postgresql://geo:geopassword@localhost:5432/flightlog \
        .venv/bin/pytest tests/test_geo.py -v
"""

import csv
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from geo.ingest import ingest

DATABASE_URL = os.environ.get("DATABASE_URL", "")
DATA_CSV = Path(__file__).parent.parent / "data" / "sample_flight.csv"

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — start PostGIS with docker compose -f docker-compose.geo.yml up",
)


@pytest.fixture(scope="module")
def csv_path(tmp_path_factory):
    """A temp copy of the sample CSV so the source_file key is test-session-unique."""
    dest = tmp_path_factory.mktemp("geo") / "test_flight.csv"
    shutil.copy(DATA_CSV, dest)
    return dest


@pytest.fixture(scope="module")
def expected_points(csv_path):
    """Count data rows in the CSV (excluding header)."""
    with open(csv_path, newline="") as fh:
        return sum(1 for _ in csv.DictReader(fh))


@pytest.fixture(scope="module")
def flight_id(csv_path):
    return ingest(str(csv_path), DATABASE_URL)


@pytest.fixture(scope="module")
def client():
    os.environ["DATABASE_URL"] = DATABASE_URL
    # Import after setting the env var so asyncpg pool creation can read it.
    from geo.api import app  # noqa: PLC0415

    with TestClient(app) as c:
        yield c


# --- ingest ---


def test_ingest_returns_positive_id(flight_id):
    assert isinstance(flight_id, int)
    assert flight_id > 0


def test_ingest_idempotent(csv_path, flight_id):
    """Running ingest twice on the same file must return the same id, not raise."""
    second_id = ingest(str(csv_path), DATABASE_URL)
    assert second_id == flight_id


# --- API ---


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_track_is_geojson_feature(client, flight_id):
    resp = client.get(f"/flights/{flight_id}/track")
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "Feature"
    assert body["properties"]["flight_id"] == flight_id


def test_track_geometry_is_linestring(client, flight_id):
    body = client.get(f"/flights/{flight_id}/track").json()
    assert body["geometry"]["type"] == "LineString"


def test_track_point_count(client, flight_id, expected_points):
    """Coordinate count must match CSV row count — no duplicates, no drops."""
    body = client.get(f"/flights/{flight_id}/track").json()
    coords = body["geometry"]["coordinates"]
    assert len(coords) == expected_points


def test_track_coordinates_are_3d(client, flight_id):
    """Each coordinate must be [lon, lat, alt] — three values (LineStringZ)."""
    body = client.get(f"/flights/{flight_id}/track").json()
    coords = body["geometry"]["coordinates"]
    assert all(len(c) == 3 for c in coords)


def test_track_unknown_flight_returns_404(client):
    resp = client.get("/flights/999999/track")
    assert resp.status_code == 404
