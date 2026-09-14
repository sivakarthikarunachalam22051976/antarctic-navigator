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
from models.drift_model import advect_iceberg, project_iceberg_rk4
from models.polar_intelligence import (
    ADVANCED_VESSELS,
    attainable_speed_kn,
    polar_safety_screen,
    polar_stereographic_xy,
    simulate_voyage,
)
from models.router import (
    ICE_EXPOSURE_LIMITS,
    MISSION_PROFILES,
    PRIORITY_PROFILES,
    ROUTE_OBJECTIVES,
    VESSEL_PROFILES,
    exposure_band,
    find_route,
)
from models.seaice_forecast import forecast_concentration


app = FastAPI(
    title="Antarctic Navigator API",
    version="1.6.0",
    description=(
        "Predictive and physics-informed Antarctic route decision-support prototype with mission-aware alternatives."
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
    allow_origin_regex=r"^https://antarctic-navigator(?:-[a-z0-9-]+)?\.vercel\.app$",
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

USE_REAL = os.getenv("USE_REAL_DATA", "1").strip() == "1"
ALLOW_SYNTHETIC_FALLBACK = os.getenv("ALLOW_SYNTHETIC_FALLBACK", "0").strip() == "1"
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

    if USE_REAL:
        if REAL.exists():
            path = REAL
        elif ALLOW_SYNTHETIC_FALLBACK and SYNTHETIC.exists():
            path = SYNTHETIC
        else:
            raise RuntimeError(
                "Real-data mode is enabled, but the real navigator bundle is missing. "
                "Refresh backend/data/real/navigator_bundle.json or explicitly set "
                "ALLOW_SYNTHETIC_FALLBACK=1 for offline testing only."
            )
    else:
        path = SYNTHETIC

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

    meta["requested_real_data"] = USE_REAL
    meta["real_data_active"] = bool(USE_REAL and path == REAL)
    meta["synthetic_fallback_active"] = bool(USE_REAL and path != REAL)
    if USE_REAL and path != REAL:
        meta["fallback_reason"] = (
            "Synthetic offline fallback explicitly enabled for testing."
        )

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
    """Project observed icebergs once with RK4 using the real forcing grids."""
    dataset = get_dataset()
    projected: list[dict[str, Any]] = []
    for iceberg in icebergs:
        try:
            projected.append(
                project_iceberg_rk4(
                    iceberg,
                    hours,
                    dataset["current_u"],
                    dataset["current_v"],
                    dataset["wind_u"],
                    dataset["wind_v"],
                    dataset["lat_grid"],
                    dataset["lon_grid"],
                    ensemble_size=5,
                )
            )
        except Exception:
            # Keep the real-data route operational even if one malformed iceberg
            # record cannot be projected.
            continue
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

        # Expand the screening field to the RK4 uncertainty ensemble so a route
        # does not treat the central trajectory as perfectly certain.
        for member in iceberg.get("ensemble", []):
            mlat = float(member.get("lat", lat))
            mlon = float(member.get("lon", lon))
            if GRID_LAT_MIN <= mlat <= GRID_LAT_MAX and GRID_LON_MIN <= mlon <= GRID_LON_MAX:
                mr, mc = latlon_to_rc(mlat, mlon)
                for rr in range(max(0, mr - 1), min(rows, mr + 2)):
                    for cc in range(max(0, mc - 1), min(cols, mc + 2)):
                        value = 0.65 * math.exp(-math.hypot(rr - mr, cc - mc) ** 2 / 2.0)
                        risk[rr, cc] = max(risk[rr, cc], value)

    # Land is never routable even if an iceberg risk calculation produces zero.
    risk[~dataset["navigable_mask"]] = 1.0
    return np.clip(risk, 0.0, 1.0)


# ---------------------------------------------------------------------------
# ROUTE DECISION SUPPORT HELPERS
# ---------------------------------------------------------------------------


def _parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _freshness_summary(meta: dict[str, Any], required_hours: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    sources: dict[str, dict[str, Any]] = {}
    ages: list[float] = []

    definitions = (
        ("sea_ice", "SEA ICE", meta.get("sea_ice_retrieved_at_utc")),
        ("icebergs", "ICEBERGS", meta.get("iceberg_retrieved_at_utc")),
        ("currents", "OCEAN CURRENTS", meta.get("current_retrieved_at_utc")),
        ("wind", "WIND", meta.get("wind_retrieved_at_utc")),
    )

    for key, label, timestamp in definitions:
        parsed = _parse_utc(timestamp)
        age_hours = None if parsed is None else max(0.0, (now - parsed).total_seconds() / 3600.0)
        if age_hours is not None:
            ages.append(age_hours)
        sources[key] = {
            "label": label,
            "retrieved_at_utc": str(timestamp or ""),
            "age_hours": None if age_hours is None else round(age_hours, 1),
            "within_requirement": (
                True if required_hours <= 0 and age_hours is not None else
                False if age_hours is None else age_hours <= required_hours
            ),
        }

    worst_age = max(ages) if ages else None
    requirement_met = (
        True if required_hours <= 0 and ages else
        False if worst_age is None else worst_age <= required_hours
    )

    return {
        "required_hours": required_hours,
        "requirement_met": requirement_met,
        "worst_age_hours": None if worst_age is None else round(worst_age, 1),
        "checked_at_utc": now.isoformat(),
        "sources": sources,
    }


def _route_risk_score(
    mean_ice: float,
    max_ice: float,
    max_iceberg_risk: float,
) -> float:
    return float(
        np.clip(
            0.50 * mean_ice + 0.30 * max_ice + 0.20 * max_iceberg_risk,
            0.0,
            1.0,
        )
    )


def _route_metrics(
    path_rc: list[tuple[int, int]],
    total_cost: float,
    target: np.ndarray,
    risk: np.ndarray,
    forecast_horizon: int,
    vessel_profile: str,
    dataset_meta: dict[str, Any],
    start_row: int,
    start_col: int,
    goal_row: int,
    goal_col: int,
    start_snapped: bool,
    goal_snapped: bool,
) -> dict[str, Any]:
    path = [rc_to_latlon(row, col) for row, col in path_rc]
    path_objects = [{"lat": lat, "lon": lon} for lat, lon in path]

    ice_values = np.asarray([target[row, col] for row, col in path_rc], dtype=float)
    risk_values = np.asarray([risk[row, col] for row, col in path_rc], dtype=float)

    mean_ice = float(ice_values.mean())
    max_ice = float(ice_values.max())
    high_ice_fraction = float(np.mean(ice_values >= 0.75))
    max_iceberg_risk = float(risk_values.max())
    risk_score = _route_risk_score(mean_ice, max_ice, max_iceberg_risk)
    assessment = (
        "High environmental exposure - human review required before operation."
        if max_ice >= 0.90 or max_iceberg_risk >= 0.75
        else "Moderate environmental exposure - review recommended."
        if max_ice >= 0.75 or max_iceberg_risk >= 0.40
        else "Lower modeled environmental exposure."
    )

    return {
        "path": path_objects,
        "waypoints": len(path_objects),
        "total_cost": float(total_cost),
        "distance_km": _distance(path_objects),
        "mean_ice_concentration": mean_ice,
        "max_ice_concentration": max_ice,
        "high_ice_fraction": high_ice_fraction,
        "max_iceberg_risk": max_iceberg_risk,
        "risk_score": risk_score,
        "exposure_band": exposure_band(risk_score),
        "route_assessment": assessment,
        "hard_ice_cells": int(np.sum(ice_values >= 1.0)),
        "horizon_days": forecast_horizon,
        "vessel_profile": vessel_profile,
        "forecast_dataset": dataset_meta,
        "requested_start": None,
        "requested_goal": None,
        "used_start": {
            "lat": rc_to_latlon(start_row, start_col)[0],
            "lon": rc_to_latlon(start_row, start_col)[1],
        },
        "used_goal": {
            "lat": rc_to_latlon(goal_row, goal_col)[0],
            "lon": rc_to_latlon(goal_row, goal_col)[1],
        },
        "start_snapped_to_ocean": start_snapped,
        "goal_snapped_to_ocean": goal_snapped,
        "trajectory_basis": dataset_meta.get("trajectory_basis", "unknown"),
    }


def _route_explanation(
    candidate: dict[str, Any],
    candidates: list[dict[str, Any]],
    max_ice_limit: float,
    freshness_met: bool,
    objective: str,
) -> list[str]:
    reasons: list[str] = []
    min_distance = min(item["distance_km"] for item in candidates)
    min_risk = min(item["risk_score"] for item in candidates)
    min_iceberg = min(item["max_iceberg_risk"] for item in candidates)

    distance_gap = 0.0 if min_distance <= 0 else (candidate["distance_km"] / min_distance - 1.0) * 100.0

    if abs(candidate["risk_score"] - min_risk) < 1e-9:
        reasons.append("Lowest combined modeled sea-ice and iceberg risk score among candidates")
    elif candidate["max_iceberg_risk"] <= min_iceberg + 1e-9:
        reasons.append("Lower projected iceberg risk")

    if candidate["distance_km"] <= min_distance + 1e-6:
        reasons.append("Shortest transit distance")
    elif distance_gap < 5.0:
        reasons.append("Near-shortest transit distance")

    if candidate["max_ice_concentration"] <= max_ice_limit:
        reasons.append("Within the selected maximum ice-exposure limit")
    else:
        reasons.append("Exceeds the selected maximum ice-exposure limit")

    if objective == "safest":
        reasons.append("Strongest environmental-risk weighting")
    elif objective == "fastest":
        reasons.append("Strongest transit-efficiency weighting")
    else:
        reasons.append("Balanced distance-versus-exposure trade-off")

    if freshness_met:
        reasons.append("Selected data-freshness requirement is met")
    else:
        reasons.append("Data-freshness requirement is not fully met; human review required")

    return reasons[:4]


def _mission_weights(mission: str, priority: str) -> dict[str, float]:
    mission_profile = MISSION_PROFILES.get(mission, MISSION_PROFILES["resupply"])
    priority_profile = PRIORITY_PROFILES.get(priority, PRIORITY_PROFILES["balanced"])
    keys = ("distance", "risk", "iceberg", "freshness")
    combined = {key: 0.5 * mission_profile["weights"][key] + 0.5 * priority_profile["weights"][key] for key in keys}
    total = sum(combined.values()) or 1.0
    return {key: value / total for key, value in combined.items()}


def _path_similarity(path_a: list[tuple[int, int]], path_b: list[tuple[int, int]]) -> float:
    if not path_a or not path_b:
        return 0.0
    overlap = len(set(path_a).intersection(path_b))
    return overlap / max(1, min(len(path_a), len(path_b)))


def _build_diversity_penalty(
    existing_paths: list[list[tuple[int, int]]],
    shape: tuple[int, int],
) -> np.ndarray:
    """Create a temporary corridor penalty used only to seek a distinct candidate."""
    penalty = np.zeros(shape, dtype=float)
    rows, cols = shape
    for path in existing_paths:
        for row, col in path:
            for rr in range(max(0, row - 2), min(rows, row + 3)):
                for cc in range(max(0, col - 2), min(cols, col + 3)):
                    grid_distance = abs(rr - row) + abs(cc - col)
                    if grid_distance == 0:
                        value = 1500.0
                    elif grid_distance == 1:
                        value = 350.0
                    else:
                        value = 100.0
                    penalty[rr, cc] = max(penalty[rr, cc], value)
    return penalty


def _select_recommended_route(
    candidates: list[dict[str, Any]],
    mission: str,
    priority: str,
    max_ice_limit: float,
    freshness: dict[str, Any],
) -> dict[str, Any]:
    fastest_distance = min(candidate["distance_km"] for candidate in candidates)
    weights = _mission_weights(mission, priority)

    for candidate in candidates:
        distance_ratio = candidate["distance_km"] / max(fastest_distance, 1e-9)
        exceedance = max(0.0, candidate["max_ice_concentration"] - max_ice_limit)
        freshness_penalty = 0.18 if not freshness["requirement_met"] and weights["freshness"] > 0 else 0.0
        limit_penalty = exceedance * 2.5
        candidate["distance_over_shortest_pct"] = max(0.0, (distance_ratio - 1.0) * 100.0)

        if priority == "safety_first":
            # Safety-first is intentionally lexicographic: first reduce modeled
            # environmental risk, then exposure limit exceedance, then distance.
            # This makes the operator's stated priority dominate small travel-time
            # differences while keeping the result explainable.
            candidate["selection_score"] = (
                candidate["risk_score"]
                + 0.55 * candidate["max_iceberg_risk"]
                + 2.5 * exceedance
                + 0.03 * max(0.0, distance_ratio - 1.0)
                + freshness_penalty
            )
        else:
            candidate["selection_score"] = (
                weights["distance"] * (distance_ratio - 1.0)
                + weights["risk"] * candidate["risk_score"]
                + weights["iceberg"] * candidate["max_iceberg_risk"]
                + limit_penalty
                + freshness_penalty
            )

    if priority == "safety_first":
        # Stable tie-breaking keeps safety first, then lower iceberg exposure,
        # then shorter distance.
        return min(
            candidates,
            key=lambda item: (
                item["risk_score"],
                item["max_iceberg_risk"],
                item["distance_km"],
            ),
        )

    return min(candidates, key=lambda item: item["selection_score"])


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

    sea_ice_source = str(meta.get("source", ""))
    sea_ice_date = str(meta.get("observation_date", ""))
    sea_ice_retrieved = str(meta.get("sea_ice_retrieved_at_utc") or meta.get("data_accessed_utc", ""))
    iceberg_source = str(meta.get("iceberg_source", ""))
    iceberg_date = str(meta.get("iceberg_observation_date", ""))
    iceberg_retrieved = str(meta.get("iceberg_retrieved_at_utc", ""))
    iceberg_count = int(meta.get("iceberg_records_used", 0) or 0)
    current_source = str(meta.get("current_source", ""))
    current_date = str(meta.get("current_observation_date", ""))
    current_retrieved = str(meta.get("current_retrieved_at_utc", ""))
    wind_source = str(meta.get("wind_source", ""))
    wind_date = str(meta.get("wind_observation_date", ""))
    wind_retrieved = str(meta.get("wind_retrieved_at_utc", ""))
    forcing = str(meta.get("environmental_forcing", ""))
    real_bundle = bool(meta.get("dataset_kind", "").startswith("real_"))

    return {
        "bundle_generated_at_utc": str(meta.get("bundle_generated_at_utc") or meta.get("data_accessed_utc", "")),
        "dataset_kind": meta.get("dataset_kind", "unknown"),
        "routing_status": (
            "All available real environmental inputs loaded"
            if forcing and "none" not in forcing.lower()
            else "Real data bundle loaded; wind/current forcing not connected"
            if real_bundle
            else "Offline synthetic demo dataset"
        ),
        "sources": {
            "sea_ice": _source_block(sea_ice_source, sea_ice_date, sea_ice_retrieved, "available" if sea_ice_date else "unknown", "SEA ICE"),
            "icebergs": _source_block(iceberg_source, iceberg_date, iceberg_retrieved, "available" if iceberg_count > 0 else "not_connected", "ICEBERGS"),
            "currents": _source_block(current_source, current_date, current_retrieved, "available" if current_source else "not_connected", "OCEAN CURRENTS"),
            "wind": _source_block(wind_source, wind_date, wind_retrieved, "available" if wind_source else "not_connected", "WIND"),
        },
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    dataset = get_dataset()
    meta = dataset["meta"]
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "dataset_kind": meta.get("dataset_kind", "unknown"),
        "source": meta.get("source", "unknown"),
        "source_date": meta.get("observation_date", ""),
        "iceberg_source": meta.get("iceberg_source", ""),
        "iceberg_records_used": meta.get("iceberg_records_used", 0),
        "environmental_forcing": meta.get("environmental_forcing", "unknown"),
        "bundle_generated_at_utc": meta.get("bundle_generated_at_utc", meta.get("data_accessed_utc", "")),
    }


@app.get("/api/data-status")
def data_status() -> dict[str, Any]:
    dataset = get_dataset()
    return _data_status_from_meta(dataset["meta"])


@app.get("/api/config")
def config() -> dict[str, Any]:
    return {
        "stations": _station_config(),
        "vessel_profiles": {
            key: {
                "label": value.get("label", key),
                "ice_class": value.get("ice_class", "screening"),
                "power_mw": value.get("power_mw"),
                "design_speed_kn": value.get("design_speed_kn"),
            }
            for key, value in VESSEL_PROFILES.items()
        },
        "advanced_vessels": ADVANCED_VESSELS,
        "route_objectives": {key: value["label"] for key, value in ROUTE_OBJECTIVES.items()},
        "mission_profiles": {
            key: {"label": value["label"], "description": value["description"]}
            for key, value in MISSION_PROFILES.items()
        },
        "priority_profiles": {
            key: {"label": value["label"]}
            for key, value in PRIORITY_PROFILES.items()
        },
        "ice_exposure_limits": ICE_EXPOSURE_LIMITS,
        "freshness_options_hours": [24, 48, 72, 168],
        "decision_intelligence": {
            "sea_ice_forecast": "Hybrid persistence + seasonal correction + semi-Lagrangian environmental advection when forcing is available",
            "iceberg_drift": "Physics-informed free-drift with RK4 integration + uncertainty ensemble",
            "vessel_risk": "Vessel-aware ice exposure and planning-performance screening",
            "route_optimisation": "Risk-aware A* graph optimisation with mission/priority ranking",
            "machine_learning": False,
            "autonomous_control": False,
        },
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
        "mission_profiles": MISSION_PROFILES,
        "priority_profiles": PRIORITY_PROFILES,
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
    horizon_days: int = Query(3, ge=1, le=7),
) -> dict[str, Any]:
    dataset = get_dataset()
    forecast = forecast_concentration(
        dataset["concentration"],
        int(dataset["meta"].get("day_of_year", 1)),
        dataset["lat_grid"],
        horizon_days,
        current_u=dataset["current_u"],
        current_v=dataset["current_v"],
        wind_u=dataset["wind_u"],
        wind_v=dataset["wind_v"],
        lon_grid=dataset["lon_grid"],
    )
    return {
        "horizon_days": horizon_days,
        "forecast": forecast.tolist(),
        "meta": dataset["meta"],
    }


@app.get("/api/icebergs")
def icebergs() -> dict[str, Any]:
    dataset = get_dataset()
    return {"icebergs": dataset["icebergs"], "meta": dataset["meta"]}


@app.get("/api/icebergs/projected")
def icebergs_projected(
    hours_ahead: int = Query(24, ge=1, le=240),
) -> dict[str, Any]:
    dataset = get_dataset()
    projected = project_icebergs(dataset["icebergs"], hours_ahead)
    return {
        "icebergs": projected,
        "meta": dataset["meta"],
        "trajectory_basis": dataset["meta"].get("trajectory_basis", "unknown"),
    }


@app.get("/api/route")
def route(
    start_lat: float,
    start_lon: float,
    goal_lat: float,
    goal_lon: float,
    horizon_days: int = Query(3, ge=1, le=7),
    vessel_profile: str = Query("standard"),
    mission: str = Query("resupply"),
    priority: str = Query("balanced"),
    max_ice_exposure: str = Query("medium"),
    freshness_requirement_hours: int = Query(48, ge=0, le=168),
) -> dict[str, Any]:
    if vessel_profile not in VESSEL_PROFILES:
        raise HTTPException(status_code=400, detail="Unknown vessel_profile.")
    if mission not in MISSION_PROFILES:
        raise HTTPException(status_code=400, detail="Unknown mission.")
    if priority not in PRIORITY_PROFILES:
        raise HTTPException(status_code=400, detail="Unknown priority.")
    if max_ice_exposure not in ICE_EXPOSURE_LIMITS:
        raise HTTPException(status_code=400, detail="Unknown max_ice_exposure.")

    dataset = get_dataset()
    start_row, start_col, start_snapped = _route_cell_for_point(start_lat, start_lon)
    goal_row, goal_col, goal_snapped = _route_cell_for_point(goal_lat, goal_lon)
    start = (start_row, start_col)
    goal = (goal_row, goal_col)

    forecast = forecast_concentration(
        dataset["concentration"],
        int(dataset["meta"].get("day_of_year", 1)),
        dataset["lat_grid"],
        horizon_days,
        current_u=dataset["current_u"],
        current_v=dataset["current_v"],
        wind_u=dataset["wind_u"],
        wind_v=dataset["wind_v"],
        lon_grid=dataset["lon_grid"],
    )
    target = forecast[horizon_days - 1]
    projected = project_icebergs(dataset["icebergs"], horizon_days * 24)
    risk = iceberg_risk_grid(projected, target.shape)
    freshness = _freshness_summary(dataset["meta"], freshness_requirement_hours)
    max_ice_limit = ICE_EXPOSURE_LIMITS[max_ice_exposure]

    candidates: list[dict[str, Any]] = []
    route_errors: list[str] = []
    objective_ids = ("safest", "fastest", "balanced")
    objective_labels = {key: value["label"] for key, value in ROUTE_OBJECTIVES.items()}

    for idx, objective in enumerate(objective_ids):
        try:
            path_rc, total_cost = find_route(
                target,
                start,
                goal,
                risk,
                vessel_profile,
                dataset["navigable_mask"],
                objective=objective,
            )

            # Route C is intentionally diversified when its objective produces
            # the same corridor as A or B. This preserves the meaning of
            # "Fastest" (shortest traversable path) while making the displayed
            # alternatives genuinely useful to the operator.
            if objective == "balanced" and candidates:
                similar = any(
                    _path_similarity(path_rc, existing["_path_rc"]) >= 0.95
                    for existing in candidates
                )
                if similar:
                    try:
                        diversity_penalty = _build_diversity_penalty(
                            [existing["_path_rc"] for existing in candidates],
                            target.shape,
                        )
                        alternative_path, alternative_cost = find_route(
                            target,
                            start,
                            goal,
                            risk,
                            vessel_profile,
                            dataset["navigable_mask"],
                            objective="balanced",
                            extra_cost_grid=diversity_penalty,
                        )
                        if all(
                            _path_similarity(alternative_path, existing["_path_rc"]) < 0.95
                            for existing in candidates
                        ):
                            path_rc, total_cost = alternative_path, alternative_cost
                    except ValueError:
                        pass
        except ValueError as error:
            route_errors.append(f"{objective_labels[objective]}: {error}")
            continue

        candidate = _route_metrics(
            path_rc,
            total_cost,
            target,
            risk,
            horizon_days,
            vessel_profile,
            dataset["meta"],
            start_row,
            start_col,
            goal_row,
            goal_col,
            start_snapped,
            goal_snapped,
        )
        candidate["id"] = chr(ord("A") + idx)
        candidate["label"] = objective_labels[objective]
        candidate["objective"] = objective
        candidate["objective_description"] = ROUTE_OBJECTIVES[objective]["description"]
        candidate["requested_start"] = {"lat": start_lat, "lon": start_lon}
        candidate["requested_goal"] = {"lat": goal_lat, "lon": goal_lon}
        candidate["polar_screening"] = polar_safety_screen(vessel_profile, candidate["max_ice_concentration"])
        candidate["_path_rc"] = path_rc
        candidates.append(candidate)

    if not candidates:
        detail = (
            "No candidate route exists through the current forecast risk field. "
            "The planner preserves 100% sea-ice and non-navigable cells as hard exclusions; "
            "try a different endpoint or forecast horizon if the current corridor is physically disconnected."
        )
        if route_errors:
            detail += " " + " | ".join(route_errors)
        raise HTTPException(status_code=422, detail=detail)

    recommended = _select_recommended_route(
        candidates,
        mission,
        priority,
        max_ice_limit,
        freshness,
    )

    fastest_distance = min(item["distance_km"] for item in candidates)
    for candidate in candidates:
        candidate["distance_over_shortest_pct"] = (
            max(0.0, (candidate["distance_km"] / max(fastest_distance, 1e-9) - 1.0) * 100.0)
        )
        candidate["within_max_ice_exposure"] = candidate["max_ice_concentration"] <= max_ice_limit
        candidate["explanation"] = _route_explanation(
            candidate,
            candidates,
            max_ice_limit,
            freshness["requirement_met"],
            candidate["objective"],
        )
        candidate["selection_score"] = round(float(candidate.get("selection_score", 0.0)), 4)
        candidate.pop("_path_rc", None)

    recommended["recommended"] = True
    recommended["recommendation_reason"] = (
        "Best mission-aware trade-off between transit distance and modeled environmental exposure "
        f"for {MISSION_PROFILES[mission]['label'].lower()} with {PRIORITY_PROFILES[priority]['label'].lower()} priority."
    )

    return {
        "path": recommended["path"],
        "waypoints": recommended["waypoints"],
        "total_cost": recommended["total_cost"],
        "distance_km": recommended["distance_km"],
        "mean_ice_concentration": recommended["mean_ice_concentration"],
        "max_ice_concentration": recommended["max_ice_concentration"],
        "high_ice_fraction": recommended["high_ice_fraction"],
        "max_iceberg_risk": recommended["max_iceberg_risk"],
        "risk_score": recommended["risk_score"],
        "exposure_band": recommended["exposure_band"],
        "route_assessment": recommended["route_assessment"],
        "hard_ice_cells": recommended["hard_ice_cells"],
        "horizon_days": recommended["horizon_days"],
        "vessel_profile": recommended["vessel_profile"],
        "forecast_dataset": recommended["forecast_dataset"],
        "requested_start": recommended["requested_start"],
        "requested_goal": recommended["requested_goal"],
        "used_start": recommended["used_start"],
        "used_goal": recommended["used_goal"],
        "start_snapped_to_ocean": recommended["start_snapped_to_ocean"],
        "goal_snapped_to_ocean": recommended["goal_snapped_to_ocean"],
        "trajectory_basis": recommended["trajectory_basis"],
        "geometry": {
            "projection": "EPSG:3031",
            "start_xy_m": [round(v, 1) for v in polar_stereographic_xy(start_lat, start_lon)],
            "goal_xy_m": [round(v, 1) for v in polar_stereographic_xy(goal_lat, goal_lon)],
        },
        "intelligence": {
            "sea_ice_forecast": "Hybrid persistence + seasonal correction + semi-Lagrangian environmental advection when forcing is available",
            "iceberg_trajectory": "Physics-informed free-drift + RK4 integration + uncertainty ensemble",
            "ship_performance": "Lindqvist-inspired relative ice-resistance planning model",
            "safety_layer": "Vessel-aware polar safety screening; POLARIS is reference context only",
            "machine_learning": False,
            "autonomous_control": False,
        },
        "mission": mission,
        "mission_label": MISSION_PROFILES[mission]["label"],
        "priority": priority,
        "priority_label": PRIORITY_PROFILES[priority]["label"],
        "max_ice_exposure": max_ice_exposure,
        "max_ice_exposure_label": f"{int(max_ice_limit * 100)}%",
        "freshness_requirement_hours": freshness_requirement_hours,
        "freshness": freshness,
        "recommendation": {
            "route_id": recommended["id"],
            "label": recommended["label"],
            "reason": recommended["recommendation_reason"],
        },
        "alternatives": candidates,
        "data_used": {
            "sea_ice": {
                "source": dataset["meta"].get("source", ""),
                "observation_date": dataset["meta"].get("observation_date", ""),
            },
            "icebergs": {
                "source": dataset["meta"].get("iceberg_source", ""),
                "observation_date": dataset["meta"].get("iceberg_observation_date", ""),
            },
            "currents": {
                "source": dataset["meta"].get("current_source", ""),
                "observation_date": dataset["meta"].get("current_observation_date", ""),
            },
            "wind": {
                "source": dataset["meta"].get("wind_source", ""),
                "analysis_date": dataset["meta"].get("wind_observation_date", ""),
            },
        },
        "human_review_required": (
            not freshness["requirement_met"]
            or not recommended["within_max_ice_exposure"]
            or recommended["route_assessment"].startswith("High")
        ),
        "candidate_warnings": route_errors,
    }



@app.get("/api/validation/robustness")
def validation_robustness(
    horizon_days: int = Query(3, ge=1, le=7),
    vessel_profile: str = Query("standard"),
) -> dict[str, Any]:
    """Run deterministic iceberg-position stress tests on the current real bundle."""
    if vessel_profile not in VESSEL_PROFILES:
        raise HTTPException(status_code=400, detail="Unknown vessel_profile.")
    dataset = get_dataset()
    if not bool(dataset["meta"].get("real_data_active")):
        raise HTTPException(status_code=503, detail="Robustness testing requires the real navigator bundle.")

    start_row, start_col, start_snapped = _route_cell_for_point(
        INDIAN_STATIONS["Maitri"]["lat"], INDIAN_STATIONS["Maitri"]["lon"]
    )
    goal_row, goal_col, goal_snapped = _route_cell_for_point(
        INDIAN_STATIONS["Bharati"]["lat"], INDIAN_STATIONS["Bharati"]["lon"]
    )
    start = (start_row, start_col)
    goal = (goal_row, goal_col)
    forecast = forecast_concentration(
        dataset["concentration"],
        int(dataset["meta"].get("day_of_year", 1)),
        dataset["lat_grid"],
        horizon_days,
        current_u=dataset["current_u"],
        current_v=dataset["current_v"],
        wind_u=dataset["wind_u"],
        wind_v=dataset["wind_v"],
        lon_grid=dataset["lon_grid"],
    )
    target = forecast[horizon_days - 1]
    projected = project_icebergs(dataset["icebergs"], horizon_days * 24)
    base_risk = iceberg_risk_grid(projected, target.shape)
    try:
        base_path, base_cost = find_route(
            target, start, goal, base_risk, vessel_profile,
            dataset["navigable_mask"], objective="balanced"
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    def path_risk(path: list[tuple[int, int]], risk_grid: np.ndarray) -> dict[str, float]:
        values = np.asarray([risk_grid[r, c] for r, c in path], dtype=float)
        return {
            "mean": float(values.mean()) if len(values) else 0.0,
            "max": float(values.max()) if len(values) else 0.0,
            "high_fraction": float(np.mean(values >= 0.75)) if len(values) else 0.0,
        }

    def move_km(lat: float, lon: float, distance_km: float, bearing_deg: float) -> tuple[float, float]:
        br = math.radians(bearing_deg)
        dlat = distance_km * math.cos(br) / 111.32
        dlon = distance_km * math.sin(br) / max(10.0, 111.32 * math.cos(math.radians(lat)))
        return lat + dlat, lon + dlon

    scenarios: list[dict[str, Any]] = []
    bearings = tuple(range(0, 360, 45))
    for distance_km in (5.0, 10.0, 20.0):
        successful = 0
        worst_baseline = 0.0
        worst_mean = 0.0
        baseline_low_risk_cases = 0
        rerouted_max: list[float] = []
        for bearing in bearings:
            shifted: list[dict[str, Any]] = []
            for item in projected:
                copy = dict(item)
                lat, lon = move_km(float(item["projected_lat"]), float(item["projected_lon"]), distance_km, float(bearing))
                copy["projected_lat"] = lat
                copy["projected_lon"] = lon
                copy["ensemble"] = []
                shifted.append(copy)
            risk_grid = iceberg_risk_grid(shifted, target.shape)
            base_path_risk = path_risk(base_path, risk_grid)
            worst_baseline = max(worst_baseline, base_path_risk["max"])
            worst_mean = max(worst_mean, base_path_risk["mean"])
            if base_path_risk["max"] < 0.75:
                baseline_low_risk_cases += 1
            try:
                reroute_path, reroute_cost = find_route(
                    target, start, goal, risk_grid, vessel_profile,
                    dataset["navigable_mask"], objective="balanced"
                )
                successful += 1
                rerouted_max.append(path_risk(reroute_path, risk_grid)["max"])
            except ValueError:
                pass
        scenarios.append({
            "perturbation_km": distance_km,
            "directions_tested": len(bearings),
            "reroute_success_rate": successful / len(bearings),
            "baseline_path_below_high_iceberg_risk_rate": baseline_low_risk_cases / len(bearings),
            "worst_case_baseline_path_max_iceberg_risk": round(worst_baseline, 4),
            "worst_case_baseline_path_mean_iceberg_risk": round(worst_mean, 4),
            "worst_case_rerouted_max_iceberg_risk": round(max(rerouted_max), 4) if rerouted_max else None,
        })

    return {
        "status": "completed",
        "method": "Deterministic radial sensitivity test: 5/10/20 km perturbations across 8 bearings.",
        "not_a_confidence_interval": True,
        "horizon_days": horizon_days,
        "vessel_profile": vessel_profile,
        "baseline": {
            "distance_km": round(_distance([{"lat": rc_to_latlon(r, c)[0], "lon": rc_to_latlon(r, c)[1]} for r, c in base_path]), 2),
            "path_max_iceberg_risk": round(path_risk(base_path, base_risk)["max"], 4),
            "waypoints": len(base_path),
        },
        "scenarios": scenarios,
        "data": {
            "dataset_kind": dataset["meta"].get("dataset_kind", ""),
            "sea_ice_observation_date": dataset["meta"].get("observation_date", ""),
            "iceberg_observation_date": dataset["meta"].get("iceberg_observation_date", ""),
        },
        "interpretation": "This is a sensitivity test, not a statistical confidence interval. Robustness is stronger when routes remain feasible and the baseline path avoids high iceberg-risk cells under the tested perturbations.",
    }


@app.get("/api/validation/status")
def validation_status() -> dict[str, Any]:
    """Expose what validation evidence is actually available locally."""
    historical = BASE / "data" / "real" / "historical" / "byu_v8.0"
    validation_dir = BASE.parent / "validation"
    files = sorted(validation_dir.glob("*.json")) if validation_dir.exists() else []
    return {
        "historical_iceberg_archive_present": historical.exists() and any(historical.rglob("*.csv")),
        "historical_seaice_files_present": any((BASE / "data" / "real" / "historical").rglob("*.nc")) if (BASE / "data" / "real" / "historical").exists() else False,
        "completed_validation_reports": [f.name for f in files],
        "scientific_claim_policy": "No accuracy metric is claimed unless it is produced from held-out historical observations.",
    }


@app.get("/api/polar-screen")
def polar_screen(
    vessel_profile: str = Query("ice_capable"),
    ice_concentration: float = Query(0.50, ge=0.0, le=1.0),
) -> dict[str, Any]:
    """Return transparent screening-level polar safety information."""
    if vessel_profile not in VESSEL_PROFILES:
        raise HTTPException(status_code=400, detail="Unknown vessel_profile.")
    result = polar_safety_screen(vessel_profile, ice_concentration)
    result["notice"] = (
        "Screening only: full IMO POLARIS requires ice type/thickness, certified vessel "
        "class data and regulatory review; this endpoint does not certify a route."
    )
    return result


@app.get("/api/geometry")
def geometry(lat: float, lon: float) -> dict[str, float]:
    _validate_latlon(lat, lon)
    x, y = polar_stereographic_xy(lat, lon)
    return {"lat": lat, "lon": lon, "epsg": 3031, "x_m": round(x, 2), "y_m": round(y, 2)}


def _grid_value_at(dataset: dict[str, Any], field: str, lat: float, lon: float) -> float:
    row, col = latlon_to_rc(lat, lon)
    return float(dataset[field][row, col])


@app.get("/api/voyage-simulation")
def voyage_simulation(
    start_lat: float,
    start_lon: float,
    goal_lat: float,
    goal_lon: float,
    horizon_days: int = Query(3, ge=1, le=7),
    vessel_profile: str = Query("ice_capable"),
    mission: str = Query("resupply"),
    priority: str = Query("balanced"),
    max_ice_exposure: str = Query("medium"),
    freshness_requirement_hours: int = Query(48, ge=0, le=168),
) -> dict[str, Any]:
    """Compute a route first, then run an hourly-ish vessel performance simulation."""
    result = route(
        start_lat=start_lat, start_lon=start_lon, goal_lat=goal_lat, goal_lon=goal_lon,
        horizon_days=horizon_days, vessel_profile=vessel_profile, mission=mission,
        priority=priority, max_ice_exposure=max_ice_exposure,
        freshness_requirement_hours=freshness_requirement_hours,
    )
    dataset = get_dataset()
    selected = result["alternatives"][next(
        i for i, item in enumerate(result["alternatives"])
        if item["id"] == result["recommendation"]["route_id"]
    )]
    path = selected["path"]
    # Risk grid at the selected forecast horizon; iceberg projection is performed once.
    forecast = forecast_concentration(
        dataset["concentration"],
        int(dataset["meta"].get("day_of_year", 1)),
        dataset["lat_grid"],
        horizon_days,
        current_u=dataset["current_u"], current_v=dataset["current_v"],
        wind_u=dataset["wind_u"], wind_v=dataset["wind_v"],
        lon_grid=dataset["lon_grid"],
    )
    projected = project_icebergs(dataset["icebergs"], horizon_days * 24)
    risk = iceberg_risk_grid(projected, forecast[horizon_days - 1].shape)
    concentration = forecast[horizon_days - 1]

    def concentration_at(lat: float, lon: float) -> float:
        row, col = latlon_to_rc(lat, lon)
        return float(concentration[row, col])

    def risk_at(lat: float, lon: float) -> float:
        row, col = latlon_to_rc(lat, lon)
        return float(risk[row, col])

    simulation = simulate_voyage(path, vessel_profile, concentration_at, risk_at)
    return {
        "route_id": result["recommendation"]["route_id"],
        "route_label": result["recommendation"]["label"],
        "vessel_profile": vessel_profile,
        "vessel": ADVANCED_VESSELS.get(vessel_profile, ADVANCED_VESSELS["standard"]),
        "simulation": simulation,
        "screening": polar_safety_screen(vessel_profile, selected["max_ice_concentration"]),
        "human_review_required": True,
        "notice": "Planning simulation only; fuel and ETA are model estimates, not measured operational performance.",
    }


@app.post("/api/reload")
def reload_dataset() -> dict[str, str]:
    global _dataset
    _dataset = None
    get_dataset()
    return {"status": "reloaded"}
