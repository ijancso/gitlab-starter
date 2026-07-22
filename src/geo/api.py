import json
import os

import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="flightlog geo API")

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        db_url = os.environ["DATABASE_URL"]
        _pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
    return _pool


@app.on_event("shutdown")
async def shutdown() -> None:
    if _pool:
        await _pool.close()


@app.get("/health")
async def health() -> JSONResponse:
    """Liveness + readiness: verifies the DB connection is actually usable."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
    return JSONResponse({"status": "ok"})


@app.get("/flights/{flight_id}/track")
async def track(flight_id: int) -> JSONResponse:
    """
    Return the flight path as a GeoJSON Feature containing a LineStringZ.

    ST_MakeLine aggregates all track_points into a single geometry, ordered by
    time_s so the line direction matches the actual flight chronology.
    ST_AsGeoJSON serialises the result to a JSON string in one DB round-trip.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Confirm the flight exists so we can return 404 vs 422.
        exists = await conn.fetchval(
            "SELECT id FROM flights WHERE id = $1", flight_id
        )
        if exists is None:
            raise HTTPException(status_code=404, detail=f"flight {flight_id} not found")

        geojson_str = await conn.fetchval(
            """
            SELECT ST_AsGeoJSON(
                ST_MakeLine(geom ORDER BY time_s)
            )
            FROM track_points
            WHERE flight_id = $1
            """,
            flight_id,
        )

    if geojson_str is None:
        raise HTTPException(status_code=404, detail=f"flight {flight_id} has no track points")

    return JSONResponse(
        {
            "type": "Feature",
            "properties": {"flight_id": flight_id},
            "geometry": json.loads(geojson_str),
        }
    )
