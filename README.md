# flightlog

A self-hosted **GitLab CI/CD pipeline that turns a drone telemetry log into a
visual flight report**. Push a flight log, and the pipeline validates it, tests
the analysis code, computes flight metrics, and renders a report image — every
run tied to the exact commit that produced it.

The report is the build's *product*: a route map coloured by altitude, with
takeoff/landing markers, plus altitude and battery charts.

![Flight report](docs/img/flight-report.png)

## What it demonstrates

- A **self-hosted GitLab CE + Runner** in Docker (see [docs/SETUP.md](docs/SETUP.md))
- A **five-stage pipeline** (`.gitlab-ci.yml`): `lint -> validate -> test -> process -> render`
- A **data-quality gate** (`validate`): schema, value ranges, monotonic time
- **Reproducible rendering**: the plot is drawn in a fixed container, so the same
  log always produces the same charts — no "works on my machine"
- **Traceable artifacts**: `metrics.json` and `flight-report.png` are produced per
  commit, alongside the test results
- Dependency discipline: only the `render` stage installs matplotlib (`[viz]`
  extra), so the earlier stages stay fast
  
## Architecture

![System architecture](docs/img/architecture.png)

## Pipeline

| Stage | What it does | Output |
|-------|--------------|--------|
| `lint`     | Static code checks (`ruff`) | — |
| `validate` | Data-quality gate on the telemetry CSV | pass/fail |
| `test`     | Unit tests + a haversine golden check (`pytest`) | JUnit + coverage |
| `process`  | Compute flight metrics | `metrics.json` (artifact) |
| `render`   | Draw the route map + charts | `flight-report.png` (artifact) |

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,viz]"

ruff check .
pytest
flightlog validate data/sample_flight.csv
flightlog report   data/sample_flight.csv --out-dir out/   # writes out/flight-report.png + out/metrics.json
```

## The telemetry format

`data/sample_flight.csv` is a synthetic but realistic log (a lawnmower survey
over Christchurch, NZ). Columns:

`time_s, lat, lon, alt_m, battery_v, speed_ms`

Regenerate it any time with `python scripts/make_sample_flight.py > data/sample_flight.csv`.

## How the GitHub repo relates to the GitLab pipeline

The pipeline runs on a **self-hosted GitLab CE** instance — that is the skill on
display. GitHub is the public showcase. The same code lives in two places via two
git remotes:

- `origin`  -> GitHub (public portfolio)
- `gitlab`  -> your local GitLab CE (runs the real `.gitlab-ci.yml`)

An optional GitHub Actions workflow (`.github/workflows/ci.yml`) mirrors the
checks and uploads the report, so the GitHub page also shows passing CI.

## Where this goes next

1. Richer visuals: takeoff/landing labels, geofence overlay, per-segment speed.
2. Multi-log dashboard + anomaly flags (battery sag, altitude breach) as an HTML report.
3. A `fetch` stage that pulls logs from a store, then a Docker image build + push
   to GitLab's registry.
4. Pipeline metrics (duration, logs processed) pushed to Prometheus + Grafana.

---

## Geospatial track service

A standalone PostGIS + FastAPI service that ingests drone telemetry and serves flight paths as GeoJSON — a runnable, queryable slice of what a production geoscience data platform looks like at small scale.

### Run it

```bash
# 1. Create your credentials file (never committed — .env is gitignored)
cp .env.example .env

# 2. Start PostGIS + the API (waits for DB health before starting the API)
docker compose -f docker-compose.geo.yml up --build -d

# 3. Ingest the sample flight (run from the project root)
DATABASE_URL=postgresql://geo:geopassword@localhost:5432/flightlog \
  python -m geo.ingest data/sample_flight.csv

# 4. Query the track
curl http://localhost:8000/flights/1/track
```

The `/health` endpoint is also available:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### Design notes

**Why PostGIS?** PostGIS gives us first-class spatial types and functions inside an ACID-compliant database. Storing raw lat/lon floats in a plain Postgres table would work for simple distance queries, but the moment you need bounding-box lookups, spatial joins, or format conversions the SQL becomes hand-rolled and fragile. With PostGIS those operations are a single function call (`ST_Within`, `ST_Intersects`, `ST_AsGeoJSON`) and they run against a spatial index rather than a full scan.

**Why idempotent ingest?** CI pipelines retry failed jobs. A data pipeline that creates duplicate rows on retry is worse than one that fails loudly — you end up with silent data corruption. The ingest script uses `INSERT ... ON CONFLICT (source_file) DO NOTHING`: if the file was already processed, the entire transaction is a no-op. This makes re-running safe without needing a separate deduplication job.

**Why build the LineString in SQL?** `ST_MakeLine(geom ORDER BY time_s)` is an aggregate function — it folds all track_points for a flight into a single geometry in one pass, with ordering guaranteed by the database. The alternative (fetching all points into Python, sorting, then constructing a GeoJSON object) costs an extra round-trip, moves sorting responsibility to application code, and requires a geometry library dependency. The SQL approach is faster, shorter, and keeps the spatial logic where the spatial data lives.

**Next steps (not built here):** authentication on the API, a tile server endpoint (`/flights/{id}/tiles/{z}/{x}/{y}`), streaming ingest for large files via `COPY`, and a Grafana dashboard backed by the PostGIS queries.

---

## License

MIT — see [LICENSE](LICENSE).
