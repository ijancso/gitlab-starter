# Design notes — flightlog geospatial track service

Personal learning document. Not a README, not for external readers.

---

## 1. The decisions

### PostGIS vs. plain lat/lon columns

**What we chose:** PostGIS — a Postgres extension that adds a `geometry` column type and a library of spatial functions.

**Alternative:** Two `REAL` columns, `lat` and `lon`. Simple, universally understood, zero extra setup.

**Why PostGIS:**
Plain columns work fine for simple tasks like "give me the lat/lon of flight 1." The moment you want anything spatial — "is this point inside this polygon?", "what flights passed within 10 km of this location?", "give me the path as a GeoJSON LineString?" — you're writing hand-rolled arithmetic in SQL or Python. That arithmetic is fiddly (earth is not flat, degrees are not metres), slow (full table scan), and easy to get wrong (lon/lat order swap bugs are extremely common).

PostGIS gives you:
- A typed column (`geometry`) that the DB understands as geometry, not just a pair of numbers.
- Functions like `ST_Distance`, `ST_Within`, `ST_Intersects` — these work correctly on spherical geometry.
- `ST_AsGeoJSON` — one function call turns a geometry into valid GeoJSON. No Python library needed.
- A spatial index (GIST) the query planner can use automatically.

The cost: you need the PostGIS extension installed, and the image is larger (`postgis/postgis` vs. plain `postgres`). For a demo or small service, this is almost always worth it.

---

### geometry(PointZ, 4326) — what SRID 4326 means, and why PointZ not Point

**SRID 4326** is the numeric identifier for the WGS-84 coordinate reference system — the same system your GPS uses. Latitude and longitude as you know them are WGS-84 coordinates. Every spatial column in PostGIS must declare its CRS so the DB knows how to interpret the numbers and can refuse to mix incompatible systems.

Common confusion: SRID 4326 uses degrees (latitude −90 to +90, longitude −180 to +180). SRID 3857 (Web Mercator, used by Google Maps tiles) uses metres. If you mix them in a spatial join you get silently wrong results — PostGIS will warn you or error if the SRIDs don't match.

**PointZ vs. Point:** `Point` is 2-D (X, Y). `PointZ` adds a Z coordinate. We store `ST_MakePoint(lon, lat, alt_m)` — lon is X, lat is Y, alt_m is Z. The Z is what makes the GeoJSON output a `LineStringZ` (3-D line) rather than a flat `LineString`. This lets any downstream tool (QGIS, Cesium, geojson.io) render the altitude as a true third dimension rather than just a property.

Note the argument order to `ST_MakePoint`: **longitude first, latitude second**. This is the WKT/GeoJSON convention (X before Y, which is easting before northing). It is the opposite of how humans say coordinates ("47.5 north, 19.0 east") and it trips everyone up at least once.

---

### The GIST index — what it does, when it helps, when it doesn't

**What a B-tree does (what you know):** A B-tree index on an integer column sorts the values in a tree. A query `WHERE id = 42` walks the tree in O(log n) time. This works because integers have a natural total order you can sort.

**What a GIST index does differently:** Geometry has no single natural total order — you can't sort 2-D points into a line the way you sort integers. GIST (Generalized Search Tree) uses a different strategy: it builds a hierarchy of *bounding boxes*. Each node in the tree stores the minimum bounding rectangle (MBR) of all the geometries below it. A spatial query (`ST_Within`, `ST_DWithin`, `ST_Intersects`) first checks bounding boxes to eliminate most of the table, then runs the exact geometry test only on the survivors.

**When GIST helps:**
- Bounding-box queries: "give me all points within this rectangle" — the index eliminates most rows in the first pass.
- `ST_DWithin(geom, reference_point, radius)` — proximity searches.
- Spatial joins between two large tables.

**When GIST does NOT help:**
- Our current query: `WHERE flight_id = $1`. This is a plain integer filter, not a spatial filter. The query planner uses the B-tree index on `flight_id` (via the FK), not the GIST index at all. The GIST index we built is unused for the `/track` endpoint as written.

So why build it? Because the next query someone will want — "which flights crossed this bounding box?", "find all flights near Christchurch airport" — needs it. A GIST index is cheap at this scale and expensive to add later (it requires a full table scan to build). We added it for the queries we expect, not the queries we have today.

---

### ON CONFLICT DO NOTHING vs. a real upsert vs. a dedupe check in Python

Three ways to handle "don't insert this row if it already exists":

**Option A — check in Python first:**
```python
existing = conn.execute("SELECT id FROM flights WHERE source_file = %s", (path,)).fetchone()
if existing:
    return existing[0]
conn.execute("INSERT INTO flights ...")
```
Problem: race condition. Two processes can both run the SELECT, both find nothing, both try to INSERT — one will fail with a unique constraint violation. This is a classic TOCTOU bug.

**Option B — ON CONFLICT DO NOTHING (what we did):**
```sql
INSERT INTO flights (source_file) VALUES (%s)
ON CONFLICT (source_file) DO NOTHING
RETURNING id
```
The database handles the race atomically. If the row already exists, the INSERT is silently skipped and `RETURNING id` gives us nothing (we do a follow-up SELECT to get the id). Safe under concurrent ingest. One round-trip.

**Option C — real upsert (ON CONFLICT DO UPDATE):**
```sql
INSERT INTO flights (source_file, imported_at) VALUES (%s, now())
ON CONFLICT (source_file) DO UPDATE SET imported_at = now()
RETURNING id
```
Use this when you want to update a field on conflict (e.g., "last seen at"). We don't have that requirement, so DO NOTHING is simpler and makes the intent clearer: "if it exists, leave it alone."

We chose **Option B** because it's atomic, correct under retries, and the semantics exactly match what we want: a file is either ingested or it isn't — we never want to partially re-ingest it.

---

### psycopg v3 vs. asyncpg

**psycopg v3** (the `psycopg` package): the standard Postgres driver for Python, version 3. Supports both sync and async. Used in `ingest.py`.

**asyncpg**: a pure-async driver, written specifically for high performance in async Python. Used in `api.py`.

Why both?

- **Ingest is a one-shot CLI script** — it runs, inserts data, exits. Sync code is simpler and easier to reason about. psycopg v3 sync is the right tool.
- **The API is an async ASGI app (FastAPI)** — it handles concurrent HTTP requests in a single thread using asyncio. A blocking sync DB call would stall the entire event loop while waiting for Postgres. asyncpg is native async and integrates cleanly with FastAPI's connection pool pattern.

The one gotcha we hit: in psycopg v3, `executemany()` was moved from the connection object to the cursor. `conn.executemany(...)` raises `AttributeError`; the correct call is:
```python
with conn.cursor() as cur:
    cur.executemany(...)
```
This changed between v2 and v3. If you're reading old Stack Overflow answers, check which version they assume.

---

### Building the LineString in SQL (ST_MakeLine) vs. assembling it in Python

**The Python approach:**
```python
rows = await conn.fetch("SELECT lon, lat, alt FROM track_points WHERE flight_id=$1 ORDER BY time_s", id)
coords = [[r['lon'], r['lat'], r['alt']] for r in rows]
geojson = {"type": "LineString", "coordinates": coords}
```

**The SQL approach (what we did):**
```sql
SELECT ST_AsGeoJSON(
    ST_MakeLine(geom ORDER BY time_s)
)
FROM track_points
WHERE flight_id = $1
```

Why SQL wins here, specifically:

1. **One round-trip instead of N+1.** The Python approach fetches all N rows to the application, then constructs geometry. The SQL approach does the aggregation and serialisation inside the DB — one query, one result.

2. **Ordering is guaranteed by the DB.** `ST_MakeLine(geom ORDER BY time_s)` is an ordered aggregate — the DB sorts before folding. In the Python approach you must remember to sort; if you forget, you get a geometrically valid but chronologically scrambled path.

3. **No Python geometry library.** If we assembled the GeoJSON manually, we'd need to get the format exactly right (coordinate order, type strings, nesting). `ST_AsGeoJSON` produces spec-compliant GeoJSON every time.

4. **Altitude is preserved automatically.** Because the column is `PointZ`, `ST_MakeLine` produces a `LineStringZ`. We get the 3-D output for free. In the Python approach you'd need to build the 3-element coordinate arrays manually and set `"type": "LineStringZ"` — easy to get wrong.

The tradeoff: the SQL is harder to read for someone who doesn't know PostGIS. For someone who does, it's concise and obviously correct.

---

### The healthcheck + depends_on pattern in compose

**The problem:** `depends_on: db` (without `condition`) only waits for the container to *start*, not for Postgres to be *ready to accept connections*. The API container starts a few seconds after the DB container, but Postgres takes several more seconds to initialise its data directory. Without the condition, the API crashes on startup with "connection refused" and Docker marks it as failed.

**What we did:**
```yaml
db:
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
    interval: 5s
    timeout: 5s
    retries: 10

api:
  depends_on:
    db:
      condition: service_healthy
```

`pg_isready` is a Postgres utility that exits 0 when the server is accepting connections. Docker runs it every 5 seconds, up to 10 times (50 seconds total). `condition: service_healthy` tells Docker to not start the API container until the DB healthcheck has passed. No sleep loops, no retry logic in application code.

The `$$` in the healthcheck test is a compose escape: a single `$` would be interpreted by compose as a variable substitution. `$$` passes a literal `$` to the shell.

---

## 2. The SQL, line by line

### Schema: creating the spatial column

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```
Loads the PostGIS extension into the current database. Idempotent — safe to run again. Without this, the `geometry` type and all `ST_*` functions don't exist.

```sql
geom geometry(PointZ, 4326) NOT NULL
```
`geometry` is the PostGIS column type. `PointZ` constrains it to 3-D points only — any attempt to insert a 2-D point will fail. `4326` is the SRID constraint — any attempt to insert a geometry with a different SRID will fail. These constraints let PostGIS catch type mismatches at write time rather than silently storing garbage.

```sql
CREATE INDEX IF NOT EXISTS track_points_geom_idx
    ON track_points USING GIST (geom);
```
`USING GIST` selects the spatial index method instead of the default B-tree. Without `USING GIST`, Postgres would try to build a B-tree on geometry values — which doesn't work because geometry has no total order.

---

### Ingest: creating the geometry

```sql
INSERT INTO track_points (flight_id, time_s, altitude, battery_v, speed_ms, geom)
VALUES (
    %s, %s, %s, %s, %s,
    ST_SetSRID(ST_MakePoint(%s, %s, %s), 4326)
)
```

`ST_MakePoint(lon, lat, alt)` — creates a `PointZ` geometry from three numbers. Arguments are X, Y, Z — which means **longitude, latitude, altitude** in that order. This is the most common source of bugs with PostGIS: people pass lat first because that's how they say coordinates out loud.

`ST_SetSRID(..., 4326)` — tags the geometry with its coordinate reference system. Without this the geometry exists but the DB doesn't know what coordinate system it's in, which breaks spatial functions and index usage. Equivalent to telling Postgres "these are WGS-84 degrees, not arbitrary numbers."

---

### Ingest: idempotent flight row

```sql
INSERT INTO flights (source_file)
VALUES (%s)
ON CONFLICT (source_file) DO NOTHING
RETURNING id
```

`ON CONFLICT (source_file)` — the conflict target is the unique constraint on `source_file`. This clause only fires when that specific constraint would be violated.

`DO NOTHING` — suppress the error, skip the insert, return no rows.

`RETURNING id` — if the insert succeeded, return the new id. If DO NOTHING fired, this returns nothing (zero rows), which is how we detect "already existed" and fall through to the follow-up SELECT.

---

### API: building the LineString

```sql
SELECT ST_AsGeoJSON(
    ST_MakeLine(geom ORDER BY time_s)
)
FROM track_points
WHERE flight_id = $1
```

`ST_MakeLine(geom ORDER BY time_s)` — an ordered aggregate function. It consumes all `geom` values from the matching rows, in ascending `time_s` order, and folds them into a single `LineStringZ`. "Ordered aggregate" means the `ORDER BY` is inside the function call, not the outer query — it controls the order of aggregation, not the order of output rows.

`ST_AsGeoJSON(...)` — serialises any PostGIS geometry to a GeoJSON string. For a `LineStringZ` the output is:
```json
{"type":"LineString","coordinates":[[lon,lat,alt], [lon,lat,alt], ...]}
```
Note: GeoJSON always uses longitude-first order. PostGIS handles this correctly because the column type is `geometry(PointZ, 4326)` — it knows these are geographic coordinates in WGS-84 and serialises accordingly.

The result is a single text value — we parse it with `json.loads()` in Python and embed it in the Feature wrapper.

---

### API: confirming the flight exists before querying track points

```sql
SELECT id FROM flights WHERE id = $1
```

We run this before the `ST_MakeLine` query. Without it, if `flight_id = 999` doesn't exist, the aggregate returns NULL (no rows to aggregate), and we'd return a 500 or a malformed response. The existence check lets us return a proper 404 with a useful message. A two-query pattern is fine here because the flight table is tiny.

---

## 3. What's simplified or weak here

**No authentication.** The API is wide open. Anyone who can reach port 8001 can read all flight tracks. In production: add an API key header check, or put the service behind a reverse proxy (nginx, Caddy) that handles auth.

**The GIST index doesn't help our current queries.** As described above: our only query filters on `flight_id` (integer), not on spatial predicates. The GIST index is dead weight for now. It earns its place the moment you add a spatial query.

**asyncpg pool is a process-global singleton.** We create it lazily on first request and never reset it. This means tests in the same process share pool state. It also means if the DB connection drops (Postgres restart, network blip), the pool is stale and requests fail until the process restarts. Production pattern: use a pool with a keepalive setting, or use `asyncpg`'s built-in connection health checking.

**Schema is applied by the ingest script, not by a migration tool.** `ingest.py` runs `schema.sql` via `conn.execute()` on every run. This works while the schema never changes. The moment you add a column or modify a type, you need to handle the ALTER TABLE separately — the `CREATE TABLE IF NOT EXISTS` won't pick up changes to existing tables. Production pattern: Alembic, Flyway, or Sqitch for versioned migrations.

**Single-node PostGIS.** The named Docker volume holds all data. If the host dies, data is gone. Production pattern: managed database (AWS RDS with PostGIS, Supabase, Neon) with automated backups, or at minimum a backup cron job with `pg_dump`.

**The sample CSV is small (190 rows).** `executemany` inserts all rows in one transaction. At 10,000+ rows this is still fine. At millions of rows per file you'd want `COPY` (Postgres's bulk-load path, ~10x faster than INSERT for large batches).

**No structured logging or metrics.** The ingest script prints to stdout. The API has no request logging. In production: structured JSON logs, a `/metrics` endpoint for Prometheus scraping, tracing headers.

**Port hardcoded to 8001 in compose** because 8000 was already in use on this specific machine. This is a one-machine workaround, not a design decision. Clean it up before using this compose file on any other host.

---

## 4. Interview questions

**Q: Why store geometry in PostGIS rather than just keeping lat, lon, alt as three float columns?**

A: Plain floats work for simple retrieval. They break down the moment you need spatial queries — proximity search, bounding-box filtering, spatial joins — because you'd be doing trigonometry in application code against a full table scan. PostGIS gives you indexed spatial predicates (`ST_DWithin`, `ST_Within`) and format conversion (`ST_AsGeoJSON`) as single function calls. The cost is the extension dependency; the benefit is correctness and performance on any non-trivial spatial query.

---

**Q: You used ON CONFLICT DO NOTHING. What's the race condition that makes a pre-check in Python unsafe?**

A: Two processes can both run `SELECT id FROM flights WHERE source_file = X`, both find nothing, and both attempt the INSERT. One succeeds; the other gets a unique constraint violation. This is a TOCTOU (time-of-check, time-of-use) race. `ON CONFLICT DO NOTHING` is a single atomic statement — the database serialises concurrent inserts against the unique constraint. There is no window between check and insert.

---

**Q: Your GIST index is never used by your current queries. Why did you build it?**

A: The current `/track` query filters on `flight_id` — an integer, served by a B-tree. The GIST index is unused today. I added it because (a) the next query anyone will want — proximity search, bounding-box filter — needs it, and (b) GIST indexes are expensive to build on large tables (full scan required) so it's better to have it in place before the table grows. At 190 rows the overhead is negligible. Fair point though — if this were a real project I'd add a comment in the schema explaining this explicitly.

---

**Q: You use asyncpg in the API and psycopg in the ingest script. Why two drivers?**

A: asyncpg is native async, which is the right fit for an ASGI web framework handling concurrent requests in one thread. Using a sync driver in an async context would block the event loop on every DB call, destroying concurrency. psycopg v3 sync is simpler for a CLI script that runs, does one thing, and exits — there's no concurrency to care about, and sync code is easier to read and debug.

---

**Q: What happens to your service if Postgres restarts while the API is running?**

A: The asyncpg connection pool holds open connections. After a Postgres restart those connections are dead. The next request that tries to acquire a connection from the pool will get a stale connection, and the query will fail. Recovery depends on asyncpg's connection validation setting — by default it doesn't proactively health-check idle connections. The process would need to restart, or the pool would need to be configured with `max_inactive_connection_lifetime` so stale connections are discarded. This is a known weakness in the current implementation.

---

**Q: Why does ST_MakeLine need an ORDER BY inside the function? What happens without it?**

A: `ST_MakeLine` is an aggregate — it folds N point geometries into one line. Without `ORDER BY time_s`, Postgres can process the rows in any order (typically physical storage order, which may not match flight chronology after UPDATEs or deletions). The resulting line would connect the points in an arbitrary order — geometrically valid but physically meaningless. The `ORDER BY` inside the aggregate function is guaranteed to apply before aggregation, unlike an outer `ORDER BY` which only affects output row order.

---

**Q: Your healthcheck uses pg_isready. What exactly does that check, and what does it miss?**

A: `pg_isready` opens a TCP connection to Postgres and sends a startup packet. If Postgres responds (even to reject the connection with "no such user"), `pg_isready` exits 0. It checks that Postgres is accepting connections, not that your specific database, user, or schema is available. In theory, Postgres could be accepting connections but your `flightlog` database isn't created yet — `pg_isready` would still pass. For this project that's acceptable. A stricter check would run `psql -c "SELECT 1"` with the actual credentials.

---

**Q: What would break first if you pointed this at a real drone survey with 10 million track points?**

A: Several things, roughly in order of pain:
1. The ingest script uses `executemany` in a single transaction — 10M rows in one transaction means a huge WAL entry and long lock hold time. Switch to `COPY` (bulk load) or batch inserts of 10K rows per transaction.
2. `ST_MakeLine` over 10M points builds a massive geometry in memory inside the DB. You'd want to pre-simplify with `ST_SimplifyPreserveTopology` before building the line, or return a decimated track for the API and store the full-res data separately.
3. The single-node PostGIS with a Docker volume has no HA and no backups. First real data loss would end this design.
4. The API pool has 5 connections max. At any meaningful request rate you'd queue up waiting for a connection. Tune `max_size` or add a read replica.

---

**Q: Your API returns the entire LineString in one response. What's the problem with this at scale, and what would you do instead?**

A: A LineString with 10M coordinates is a multi-megabyte JSON blob. It's slow to serialize, slow to transmit, and most clients can't render it meaningfully at full resolution anyway. Production options: (1) return a simplified/decimated track by default (`ST_SimplifyPreserveTopology`) with a `?full=true` flag for the original; (2) expose a tile endpoint (`/flights/{id}/tiles/{z}/{x}/{y}`) using `ST_AsMVT` so clients only fetch the geometry for the visible zoom level; (3) stream the response rather than buffering it. We mentioned the tile endpoint as a next step in the README but didn't build it — it would be the right first scaling addition.
