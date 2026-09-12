"""Antarctic Navigator FastAPI backend."""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from config import (
    GRID_LAT_MAX,
    GRID_LAT_MIN,
    GRID_LON_MAX,
    GRID_LON_MIN,
    GRID_ROWS,
    INDIAN_STATIONS,
    latlon_to_rc,
    rc_to_latlon,
)
from models.drift_model import advect_iceberg
from models.router import VESSEL_PROFILES, find_route
from models.seaice_forecast import forecast_concentration


app = FastAPI(
    title="Antarctic Navigator API",
    version="1.3.0",
    description=(
        "Sea-ice, iceberg trajectory and route decision support prototype."
    ),
)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

frontend_url = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

for origin in frontend_url.split(","):
    clean = origin.strip().rstrip("/")
    if clean and clean not in allowed_origins:
        allowed_origins.append(clean)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# DATA PATHS
# ---------------------------------------------------------------------------

BASE = Path(__file__).resolve().parent
SYNTHETIC = BASE / "data" / "sample" / "synthetic_dataset.json"
REAL = BASE / "data" / "real" / "navigator_bundle.json"

USE_REAL = os.getenv("USE_REAL_DATA", "0").strip() == "1"
_dataset: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# DATASET LOADING
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(
        encoding="utf-8"
    ) as file:
        return json.load(file)


def _normalise_navigable_mask(
    raw: Any,
    shape: tuple[int, int],
) -> np.ndarray:
    if raw is None:
        return np.ones(shape, dtype=bool)

    mask = np.asarray(raw, dtype=bool)
    if mask.shape != shape:
        return np.ones(shape, dtype=bool)
    return mask


def get_dataset() -> dict[str, Any]:
    global _dataset

    if _dataset is not None:
        return _dataset

    path = REAL if USE_REAL and REAL.exists() else SYNTHETIC
    if not path.exists():
        raise RuntimeError(f"Dataset not found: {path}")

    raw = _load_json(path)
    concentration = np.asarray(
        raw["concentration"],
        dtype=float,
    )
    shape = concentration.shape

    meta = dict(
        raw.get("meta", {})
    )

    if USE_REAL and path != REAL:
        meta["requested_real_data"] = True
        meta["fallback_reason"] = (
            "Real bundle not found; synthetic offline dataset is being used."
        )
    else:
        meta["requested_real_data"] = USE_REAL

    meta.setdefault(
        "source",
        "Offline synthetic demo",
    )

    _dataset = {
        "meta": meta,
        "lat_grid": np.asarray(
            raw["lat_grid"],
            dtype=float,
        ),
        "lon_grid": np.asarray(
            raw["lon_grid"],
            dtype=float,
        ),
        "concentration": concentration,
        "current_u": np.asarray(
            raw.get(
                "current_u",
                np.zeros(shape),
            ),
            dtype=float,
        ),
        "current_v": np.asarray(
            raw.get(
                "current_v",
                np.zeros(shape),
            ),
            dtype=float,
        ),
        "wind_u": np.asarray(
            raw.get(
                "wind_u",
                np.zeros(shape),
            ),
            dtype=float,
        ),
        "wind_v": np.asarray(
            raw.get(
                "wind_v",
                np.zeros(shape),
            ),
            dtype=float,
        ),
        "icebergs": raw.get(
            "icebergs",
            [],
        ),
        "navigable_mask": _normalise_navigable_mask(
            raw.get("navigable_mask"),
            shape,
        ),
    }

    return _dataset


# ---------------------------------------------------------------------------
# GEOSPATIAL HELPERS
# ---------------------------------------------------------------------------


def _validate_latlon(lat: float, lon: float) -> None:
    if not (
        GRID_LAT_MIN <= lat <= GRID_LAT_MAX
        and GRID_LON_MIN <= lon <= GRID_LON_MAX
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Point is outside the Antarctic Navigator operating grid. "
                f"Latitude must be {GRID_LAT_MIN}..{GRID_LAT_MAX}; "
                f"longitude must be {GRID_LON_MIN}..{GRID_LON_MAX}."
            ),
        )


def _nearest_navigable_rc(
    lat: float,
    lon: float,
) -> tuple[int, int]:
    dataset = get_dataset()
    navigable = dataset["navigable_mask"]

    if not np.any(navigable):
        raise ValueError("The dataset contains no navigable ocean cells.")

    target_lat = math.radians(lat)
    lat_values = dataset["lat_grid"][navigable]
    lon_values = dataset["lon_grid"][navigable]

    # Small-area equirectangular approximation is sufficient for selecting the
    # nearest cell on this 10-degree-latitude Antarctic operating window.
    dx = np.radians(lon_values - lon) * math.cos(target_lat)
    dy = np.radians(lat_values - lat)
    index = int(np.argmin(dx * dx + dy * dy))

    coords = np.argwhere(navigable)
    row, col = coords[index]
    return int(row), int(col)


def _route_cell_for_point(
    lat: float,
    lon: float,
) -> tuple[int, int, bool]:
    _validate_latlon(lat, lon)
    dataset = get_dataset()
    rc = latlon_to_rc(lat, lon)

    if dataset["navigable_mask"][rc]:
        return rc[0], rc[1], False

    snapped = _nearest_navigable_rc(lat, lon)
    return snapped[0], snapped[1], True


def _station_config() -> dict[str, Any]:
    output: dict[str, Any] = {}

    for name, point in INDIAN_STATIONS.items():
        row, col = _nearest_navigable_rc(
            point["lat"],
            point["lon"],
        )
        route_lat, route_lon = rc_to_latlon(row, col)
        output[name] = {
            **point,
            "route_lat": route_lat,
            "route_lon": route_lon,
            "route_note": (
                "Route endpoint is the nearest navigable ocean grid cell; "
                "the marker itself remains at the research-station coordinate."
            ),
        }

    return output


def _distance(points: list[dict[str, float]]) -> float:
    total = 0.0
    radius_km = 6371.0088

    for first, second in zip(
        points,
        points[1:],
    ):
        lat1 = math.radians(first["lat"])
        lat2 = math.radians(second["lat"])
        dlat = math.radians(
            second["lat"] - first["lat"]
        )
        dlon = math.radians(
            second["lon"] - first["lon"]
        )

        x = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(lat1)
            * math.cos(lat2)
            * math.sin(dlon / 2.0) ** 2
        )

        total += radius_km * 2.0 * math.asin(
            min(1.0, math.sqrt(x))
        )

    return float(total)


# ---------------------------------------------------------------------------
# ICEBERG PROJECTION / RISK
# ---------------------------------------------------------------------------


def project_icebergs(
    icebergs: list[dict[str, Any]],
    hours: int,
) -> list[dict[str, Any]]:
    """Project observed icebergs once to the requested horizon."""
    dataset = get_dataset()
    projected: list[dict[str, Any]] = []

    steps = max(
        1,
        math.ceil(hours / 6),
    )

    for iceberg in icebergs:
        lat = float(iceberg["lat"])
        lon = float(iceberg["lon"])

        for _ in range(steps):
            row, col = latlon_to_rc(
                lat,
                lon,
            )

            lat, lon = advect_iceberg(
                lat,
                lon,
                (
                    dataset["current_u"][row, col],
                    dataset["current_v"][row, col],
                ),
                (
                    dataset["wind_u"][row, col],
                    dataset["wind_v"][row, col],
                ),
                6,
            )

        projected.append(
            {
                **iceberg,
                "projected_lat": lat,
                "projected_lon": lon,
                "hours_ahead": hours,
            }
        )

    return projected


def iceberg_risk_grid(
    projected_icebergs: list[dict[str, Any]],
    shape: tuple[int, int],
) -> np.ndarray:
    """Build risk around already-projected iceberg positions."""
    dataset = get_dataset()
    risk = np.zeros(
        shape,
        dtype=float,
    )

    rows, cols = shape

    for iceberg in projected_icebergs:
        lat = float(
            iceberg["projected_lat"]
        )
        lon = float(
            iceberg["projected_lon"]
        )

        if not (
            GRID_LAT_MIN <= lat <= GRID_LAT_MAX
            and GRID_LON_MIN <= lon <= GRID_LON_MAX
        ):
            continue

        row, col = latlon_to_rc(
            lat,
            lon,
        )

        # Approximate radius in grid cells from the longest axis.
        cell_lat_km = abs(
            GRID_LAT_MAX - GRID_LAT_MIN
        ) * 111.32 / max(
            1,
            GRID_ROWS - 1,
        )
        radius = max(
            1,
            int(
                math.ceil(
                    max(
                        1.0,
                        float(
                            iceberg.get(
                                "length_km",
                                2.0,
                            )
                        ),
                    )
                    / max(1.0, cell_lat_km)
                )
            ),
        )

        for rr in range(
            max(0, row - radius),
            min(rows, row + radius + 1),
        ):
            for cc in range(
                max(0, col - radius),
                min(cols, col + radius + 1),
            ):
                value = math.exp(
                    -math.hypot(
                        rr - row,
                        cc - col,
                    ) ** 2
                    / max(
                        1.0,
                        radius**2,
                    )
                )
                risk[rr, cc] = max(
                    risk[rr, cc],
                    value,
                )

    # Land is never routable even if an iceberg risk calculation produces zero.
    risk[~dataset["navigable_mask"]] = 1.0
    return np.clip(risk, 0.0, 1.0)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "Antarctic Navigator API",
        "status": "ok",
        "health": "/api/health",
        "docs": "/docs",
    }


def _data_status_from_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Return a structured provenance/freshness view for the current bundle."""
    def _source_block(
        source: str,
        observation_date: str,
        retrieved_at: str,
        status: str,
        label: str,
    ) -> dict[str, str]:
        return {
            "label": label,
            "source": source or "Not connected",
            "observation_date": observation_date or "",
            "retrieved_at_utc": retrieved_at or "",
            "status": status,
        }

    sea_ice_source = str(
        meta.get("source", "")
    )
    sea_ice_date = str(
        meta.get("observation_date", "")
    )
    sea_ice_retrieved = str(
        meta.get("sea_ice_retrieved_at_utc")
        or meta.get("data_accessed_utc", "")
    )

    iceberg_source = str(
        meta.get("iceberg_source", "")
    )
    iceberg_date = str(
        meta.get("iceberg_observation_date", "")
    )
    iceberg_retrieved = str(
        meta.get("iceberg_retrieved_at_utc", "")
    )
    iceberg_count = int(
        meta.get("iceberg_records_used", 0) or 0
    )

    current_source = str(
        meta.get("current_source", "")
    )
    current_date = str(
        meta.get("current_observation_date", "")
    )
    current_retrieved = str(
        meta.get("current_retrieved_at_utc", "")
    )

    wind_source = str(
        meta.get("wind_source", "")
    )
    wind_date = str(
        meta.get("wind_observation_date", "")
    )
    wind_retrieved = str(
        meta.get("wind_retrieved_at_utc", "")
    )

    forcing = str(
        meta.get("environmental_forcing", "")
    )
    real_bundle = bool(
        meta.get("dataset_kind", "").startswith("real_")
    )

    return {
        "bundle_generated_at_utc": str(
            meta.get("bundle_generated_at_utc")
            or meta.get("data_accessed_utc", "")
        ),
        "dataset_kind": meta.get(
            "dataset_kind", "unknown"
        ),
        "routing_status": (
            "All available real environmental inputs loaded"
            if forcing and "none" not in forcing.lower()
            else (
                "Real data bundle loaded; wind/current forcing not connected"
                if real_bundle
                else "Offline synthetic demo dataset"
            )
        ),
        "sources": {
            "sea_ice": _source_block(
                sea_ice_source,
                sea_ice_date,
                sea_ice_retrieved,
                "available" if sea_ice_date else "unknown",
                "SEA ICE",
            ),
            "icebergs": _source_block(
                iceberg_source,
                iceberg_date,
                iceberg_retrieved,
                "available" if iceberg_count > 0 else "not_connected",
                "ICEBERGS",
            ),
            "currents": _source_block(
                current_source,
                current_date,
                current_retrieved,
                "available" if current_source else "not_connected",
                "OCEAN CURRENTS",
            ),
            "wind": _source_block(
                wind_source,
                wind_date,
                wind_retrieved,
                "available" if wind_source else "not_connected",
                "WIND",
            ),
        },
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    dataset = get_dataset()
    meta = dataset["meta"]

    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "dataset_kind": meta.get(
            "dataset_kind",
            "unknown",
        ),
        "source": meta.get(
            "source",
            "unknown",
        ),
        "source_date": meta.get(
            "observation_date",
            "",
        ),
        "iceberg_source": meta.get(
            "iceberg_source",
            "",
        ),
        "iceberg_records_used": meta.get(
            "iceberg_records_used",
            0,
        ),
        "environmental_forcing": meta.get(
            "environmental_forcing",
            "unknown",
        ),
        "bundle_generated_at_utc": meta.get(
            "bundle_generated_at_utc",
            meta.get("data_accessed_utc", ""),
        ),
    }


@app.get("/api/data-status")
def data_status() -> dict[str, Any]:
    """Return exact source dates and ingestion timestamps for the UI."""
    dataset = get_dataset()
    return _data_status_from_meta(dataset["meta"])


@app.get("/api/config")
def config() -> dict[str, Any]:
    return {
        "stations": _station_config(),
        "vessel_profiles": list(
            VESSEL_PROFILES
        ),
        "grid": {
            "lat_min": GRID_LAT_MIN,
            "lat_max": GRID_LAT_MAX,
            "lon_min": GRID_LON_MIN,
            "lon_max": GRID_LON_MAX,
        },
    }


@app.get("/api/demo")
def demo() -> dict[str, Any]:
    dataset = get_dataset()
    return {
        "dataset": dataset["meta"],
        "stations": _station_config(),
        "vessel_profiles": list(VESSEL_PROFILES),
    }

@app.get('/api/data-status')
def data_status():
    d = get_dataset()
    meta = d['meta']

    return {
        "dataset_kind": meta.get("dataset_kind", "unknown"),
        "environmental_forcing": meta.get(
            "environmental_forcing",
            "none"
        ),

        "bundle_generated_at_utc": meta.get(
            "bundle_generated_at_utc",
            ""
        ),

        "sea_ice": {
            "source": meta.get(
                "source",
                "NOAA/NSIDC G10016 Version 4"
            ),
            "dataset": meta.get(
                "sea_ice_dataset",
                "G10016"
            ),
            "version": meta.get(
                "sea_ice_version",
                "4"
            ),
            "observation_date": meta.get(
                "observation_date",
                ""
            ),
            "retrieved_at_utc": meta.get(
                "sea_ice_retrieved_at_utc",
                ""
            ),
            "source_file": meta.get(
                "source_file",
                ""
            ),
        },

        "icebergs": {
            "source": meta.get(
                "iceberg_source",
                "U.S. National Ice Center (USNIC)"
            ),
            "observation_date": meta.get(
                "iceberg_observation_date",
                ""
            ),
            "retrieved_at_utc": meta.get(
                "iceberg_retrieved_at_utc",
                ""
            ),
            "source_file": meta.get(
                "iceberg_source_file",
                ""
            ),
            "records_used": meta.get(
                "iceberg_records_used",
                len(d.get("icebergs", []))
            ),
        },

        "currents": {
            "source": meta.get(
                "current_source",
                "NASA/JPL PO.DAAC OSCAR NRT V2.0"
            ),
            "observation_date": meta.get(
                "current_observation_date",
                ""
            ),
            "retrieved_at_utc": meta.get(
                "current_retrieved_at_utc",
                ""
            ),
            "source_file": meta.get(
                "current_source_file",
                ""
            ),
        },

        "wind": {
            "source": meta.get(
                "wind_source",
                "Copernicus/ECMWF ERA5"
            ),
            "analysis_date": meta.get(
                "wind_observation_date",
                ""
            ),
            "retrieved_at_utc": meta.get(
                "wind_retrieved_at_utc",
                ""
            ),
            "source_file": meta.get(
                "wind_source_file",
                ""
            ),
        },

        # Compatibility fields for simpler frontend consumers.
        "observation_date": meta.get(
            "observation_date",
            ""
        ),
        "sea_ice_observation_date": meta.get(
            "observation_date",
            ""
        ),
        "sea_ice_retrieved_at_utc": meta.get(
            "sea_ice_retrieved_at_utc",
            ""
        ),
        "iceberg_observation_date": meta.get(
            "iceberg_observation_date",
            ""
        ),
        "iceberg_retrieved_at_utc": meta.get(
            "iceberg_retrieved_at_utc",
            ""
        ),
        "current_observation_date": meta.get(
            "current_observation_date",
            ""
        ),
        "current_retrieved_at_utc": meta.get(
            "current_retrieved_at_utc",
            ""
        ),
        "wind_observation_date": meta.get(
            "wind_observation_date",
            ""
        ),
        "wind_retrieved_at_utc": meta.get(
            "wind_retrieved_at_utc",
            ""
        ),
    }


@app.get("/api/seaice/grid")
def seaice_grid() -> dict[str, Any]:
    dataset = get_dataset()
    return {
        "lat": dataset["lat_grid"].tolist(),
        "lon": dataset["lon_grid"].tolist(),
        "concentration": dataset["concentration"].tolist(),
        "meta": dataset["meta"],
    }


@app.get("/api/seaice/forecast")
def seaice_forecast(
    horizon_days: int = Query(
        3,
        ge=1,
        le=7,
    ),
) -> dict[str, Any]:
    dataset = get_dataset()
    forecast = forecast_concentration(
        dataset["concentration"],
        int(
            dataset["meta"].get(
                "day_of_year",
                1,
            )
        ),
        dataset["lat_grid"],
        horizon_days,
    )

    return {
        "horizon_days": horizon_days,
        "forecast": forecast.tolist(),
        "meta": dataset["meta"],
    }


@app.get("/api/icebergs")
def icebergs() -> dict[str, Any]:
    dataset = get_dataset()
    return {
        "icebergs": dataset["icebergs"],
        "meta": dataset["meta"],
    }


@app.get("/api/icebergs/projected")
def icebergs_projected(
    hours_ahead: int = Query(
        24,
        ge=1,
        le=240,
    ),
) -> dict[str, Any]:
    dataset = get_dataset()
    projected = project_icebergs(
        dataset["icebergs"],
        hours_ahead,
    )

    return {
        "icebergs": projected,
        "meta": dataset["meta"],
        "trajectory_basis": dataset["meta"].get(
            "trajectory_basis",
            "unknown",
        ),
    }


@app.get("/api/route")
def route(
    start_lat: float,
    start_lon: float,
    goal_lat: float,
    goal_lon: float,
    horizon_days: int = Query(
        3,
        ge=1,
        le=7,
    ),
    vessel_profile: str = Query(
        "standard"
    ),
) -> dict[str, Any]:
    if vessel_profile not in VESSEL_PROFILES:
        raise HTTPException(
            status_code=400,
            detail="Unknown vessel_profile.",
        )

    dataset = get_dataset()

    start_row, start_col, start_snapped = _route_cell_for_point(
        start_lat,
        start_lon,
    )
    goal_row, goal_col, goal_snapped = _route_cell_for_point(
        goal_lat,
        goal_lon,
    )

    start = (start_row, start_col)
    goal = (goal_row, goal_col)

    forecast = forecast_concentration(
        dataset["concentration"],
        int(
            dataset["meta"].get(
                "day_of_year",
                1,
            )
        ),
        dataset["lat_grid"],
        horizon_days,
    )
    target = forecast[horizon_days - 1]

    projected = project_icebergs(
        dataset["icebergs"],
        horizon_days * 24,
    )
    risk = iceberg_risk_grid(
        projected,
        target.shape,
    )

    try:
        path_rc, total_cost = find_route(
            target,
            start,
            goal,
            risk,
            vessel_profile,
            dataset["navigable_mask"],
        )
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    path = [
        rc_to_latlon(
            row,
            col,
        )
        for row, col in path_rc
    ]

    path_objects = [
        {
            "lat": lat,
            "lon": lon,
        }
        for lat, lon in path
    ]

    ice_values = np.asarray(
        [
            target[row, col]
            for row, col in path_rc
        ],
        dtype=float,
    )
    risk_values = np.asarray(
        [
            risk[row, col]
            for row, col in path_rc
        ],
        dtype=float,
    )

    mean_ice = float(ice_values.mean())
    max_ice = float(ice_values.max())
    high_ice_fraction = float(np.mean(ice_values >= 0.75))
    max_iceberg_risk = float(risk_values.max())

    if max_ice >= 0.90 or max_iceberg_risk >= 0.75:
        route_assessment = (
            "High environmental exposure - human review required before operation."
        )
    elif max_ice >= 0.75 or max_iceberg_risk >= 0.40:
        route_assessment = (
            "Moderate environmental exposure - review recommended."
        )
    else:
        route_assessment = "Lower modeled environmental exposure."

    actual_start_lat, actual_start_lon = rc_to_latlon(
        start_row,
        start_col,
    )
    actual_goal_lat, actual_goal_lon = rc_to_latlon(
        goal_row,
        goal_col,
    )

    return {
        "path": path_objects,
        "waypoints": len(path_objects),
        "total_cost": total_cost,
        "distance_km": _distance(path_objects),
        "mean_ice_concentration": mean_ice,
        "max_ice_concentration": max_ice,
        "high_ice_fraction": high_ice_fraction,
        "max_iceberg_risk": max_iceberg_risk,
        "route_assessment": route_assessment,
        "hard_ice_cells": int(np.sum(ice_values >= 1.0)),
        "horizon_days": horizon_days,
        "vessel_profile": vessel_profile,
        "forecast_dataset": dataset["meta"],
        "requested_start": {
            "lat": start_lat,
            "lon": start_lon,
        },
        "requested_goal": {
            "lat": goal_lat,
            "lon": goal_lon,
        },
        "used_start": {
            "lat": actual_start_lat,
            "lon": actual_start_lon,
        },
        "used_goal": {
            "lat": actual_goal_lat,
            "lon": actual_goal_lon,
        },
        "start_snapped_to_ocean": start_snapped,
        "goal_snapped_to_ocean": goal_snapped,
        "trajectory_basis": dataset["meta"].get(
            "trajectory_basis",
            "unknown",
        ),
    }


@app.post("/api/reload")
def reload_dataset() -> dict[str, str]:
    global _dataset
    _dataset = None
    get_dataset()
    return {
        "status": "reloaded"
    }
