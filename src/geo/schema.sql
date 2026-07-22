-- Enable the PostGIS extension (idempotent: no-op if already present).
CREATE EXTENSION IF NOT EXISTS postgis;

-- flights: one row per ingested CSV file.
CREATE TABLE IF NOT EXISTS flights (
    id          SERIAL PRIMARY KEY,
    source_file TEXT        NOT NULL UNIQUE,  -- used for idempotent ingest deduplication
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- track_points: one row per telemetry sample.
-- geom stores a 3-D point: ST_MakePoint(lon, lat, alt_m) in WGS-84 (SRID 4326).
-- PointZ = 3-D variant of the Point geometry type.
CREATE TABLE IF NOT EXISTS track_points (
    id         BIGSERIAL PRIMARY KEY,
    flight_id  INTEGER     NOT NULL REFERENCES flights(id) ON DELETE CASCADE,
    time_s     REAL        NOT NULL,
    altitude   REAL        NOT NULL,
    battery_v  REAL        NOT NULL,
    speed_ms   REAL        NOT NULL,
    geom       geometry(PointZ, 4326) NOT NULL
);

-- GIST (Generalized Search Tree) is PostGIS's standard spatial index type.
-- It indexes bounding boxes so spatial queries skip irrelevant rows fast.
CREATE INDEX IF NOT EXISTS track_points_geom_idx
    ON track_points USING GIST (geom);
