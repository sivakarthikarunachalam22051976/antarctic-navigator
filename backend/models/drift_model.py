"""Physics-informed iceberg drift with RK4 integration and uncertainty."""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from models.polar_intelligence import rk4_iceberg_step


def advect_iceberg(lat, lon, current_uv, wind_uv, dt_hours=6.0):
    """Backward-compatible single-step free-drift approximation."""
    uc, vc = map(float, current_uv)
    uw, vw = map(float, wind_uv)
    angle = math.radians(20 + 18 * max(0, min(1, (abs(lat) - 60) / 20)))
    uwr = uw * math.cos(angle) - vw * math.sin(angle)
    vwr = uw * math.sin(angle) + vw * math.cos(angle)
    u = uc + 0.018 * uwr
    v = vc + 0.018 * vwr
    sec = float(dt_hours) * 3600
    mlat = 111320
    mlon = max(10000, 111320 * math.cos(math.radians(lat)))
    return lat + v * sec / mlat, lon + u * sec / mlon


def _bilinear(grid: np.ndarray, lat_grid: np.ndarray, lon_grid: np.ndarray, lat: float, lon: float) -> float:
    """Nearest-neighbour sample for stable offline operation on the common grid."""
    lat_values = np.asarray(lat_grid)
    lon_values = np.asarray(lon_grid)
    lat_axis = lat_values[:, 0] if lat_values.ndim == 2 else lat_values
    lon_axis = lon_values[0, :] if lon_values.ndim == 2 else lon_values
    r = int(np.argmin(np.abs(lat_axis - lat)))
    c = int(np.argmin(np.abs(lon_axis - lon)))
    return float(grid[r, c])


def project_iceberg_rk4(
    iceberg: dict[str, Any],
    hours: int,
    current_u: np.ndarray,
    current_v: np.ndarray,
    wind_u: np.ndarray,
    wind_v: np.ndarray,
    lat_grid: np.ndarray,
    lon_grid: np.ndarray,
    ensemble_size: int = 5,
) -> dict[str, Any]:
    """Project one observed iceberg using RK4 and a small uncertainty ensemble."""
    base_lat = float(iceberg["lat"])
    base_lon = float(iceberg["lon"])
    steps = max(1, int(math.ceil(hours / 6.0)))

    def velocity_at(lat: float, lon: float) -> tuple[float, float]:
        uc = _bilinear(current_u, lat_grid, lon_grid, lat, lon)
        vc = _bilinear(current_v, lat_grid, lon_grid, lat, lon)
        uw = _bilinear(wind_u, lat_grid, lon_grid, lat, lon)
        vw = _bilinear(wind_v, lat_grid, lon_grid, lat, lon)
        angle = math.radians(20 + 18 * max(0, min(1, (abs(lat) - 60) / 20)))
        uwr = uw * math.cos(angle) - vw * math.sin(angle)
        vwr = uw * math.sin(angle) + vw * math.cos(angle)
        return uc + 0.018 * uwr, vc + 0.018 * vwr

    lat, lon = base_lat, base_lon
    for _ in range(steps):
        lat, lon = rk4_iceberg_step(lat, lon, 6.0, velocity_at)

    # Ensemble radius scales gently with horizon; this is uncertainty screening,
    # not a statistical confidence interval.
    uncertainty_km = max(2.0, 0.35 * math.sqrt(float(hours)))
    ensemble: list[dict[str, float]] = []
    for i in range(max(1, ensemble_size)):
        angle = 2 * math.pi * i / max(1, ensemble_size)
        dlat = (uncertainty_km / 111.32) * math.sin(angle)
        dlon = (uncertainty_km / max(10.0, 111.32 * math.cos(math.radians(lat)))) * math.cos(angle)
        ensemble.append({"lat": float(lat + dlat), "lon": float(lon + dlon)})

    return {
        **iceberg,
        "projected_lat": float(lat),
        "projected_lon": float(lon),
        "hours_ahead": int(hours),
        "trajectory_method": "RK4 free-drift integration",
        "uncertainty_radius_km": round(uncertainty_km, 2),
        "ensemble": ensemble,
    }
