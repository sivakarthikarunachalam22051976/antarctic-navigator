"""Transparent Antarctic sea-ice forecasting.

The serving forecast is deliberately hybrid rather than a black box:

1. persistence provides a strong, stable baseline;
2. a small seasonal correction handles systematic annual phase;
3. when real ocean-current / wind forcing is available, a semi-Lagrangian
   advection step moves the observed concentration field with the supplied
   environmental velocity;
4. the physics signal is blended conservatively with persistence so a weak or
   missing forcing field cannot destabilise the forecast.

This is a physics/statistical prototype, not a trained ML forecast and not an
operational navigation certification model.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np


_EARTH_RADIUS_M = 6_371_008.8


def _axes(grid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    arr = np.asarray(grid, dtype=float)
    if arr.ndim == 1:
        raise ValueError("A 2-D grid is required for lat/lon sampling.")
    return arr[:, 0], arr[0, :]


def _nearest_sample(
    field: np.ndarray,
    lat_axis: np.ndarray,
    lon_axis: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
) -> np.ndarray:
    """Stable nearest-cell sampling for the prototype's regular grid."""
    r = np.abs(lat_axis[:, None, None] - lat[None, :, :]).argmin(axis=0)
    c = np.abs(lon_axis[:, None, None] - lon[None, :, :]).argmin(axis=0)
    return np.asarray(field)[r, c]


def _velocity_degrees_per_hour(
    lat: np.ndarray,
    current_u: np.ndarray,
    current_v: np.ndarray,
    wind_u: Optional[np.ndarray],
    wind_v: Optional[np.ndarray],
    lat_axis: np.ndarray,
    lon_axis: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Convert forcing fields from m/s to degree/hour at grid cells.

    A small wind-drag term is used as an environmental forcing contribution,
    matching the simplified free-drift treatment already used by the iceberg
    model. It is intentionally not presented as a full sea-ice dynamics model.
    """
    cu = np.asarray(current_u, dtype=float)
    cv = np.asarray(current_v, dtype=float)
    if cu.shape != cv.shape:
        raise ValueError("current_u and current_v must have matching shapes.")

    if wind_u is None or wind_v is None:
        wu = np.zeros_like(cu)
        wv = np.zeros_like(cv)
    else:
        wu = np.asarray(wind_u, dtype=float)
        wv = np.asarray(wind_v, dtype=float)
        if wu.shape != cu.shape or wv.shape != cu.shape:
            raise ValueError("Wind and current forcing grids must match concentration shape.")

    # Use the same small wind contribution as the iceberg free-drift model.
    wind_factor = 0.018
    u = cu + wind_factor * wu
    v = cv + wind_factor * wv

    metres_per_degree_lat = 111_320.0
    metres_per_degree_lon = np.maximum(
        10_000.0,
        metres_per_degree_lat * np.cos(np.radians(np.clip(lat, -89.0, 89.0))),
    )
    dlat = v * 3600.0 / metres_per_degree_lat
    dlon = u * 3600.0 / metres_per_degree_lon
    return dlat, dlon


def _semi_lagrangian_step(
    concentration: np.ndarray,
    lat_grid: np.ndarray,
    lon_grid: np.ndarray,
    current_u: np.ndarray,
    current_v: np.ndarray,
    wind_u: Optional[np.ndarray],
    wind_v: Optional[np.ndarray],
    hours: float,
) -> np.ndarray:
    """Advect concentration backwards along the supplied surface forcing."""
    base = np.asarray(concentration, dtype=float)
    lat_axis, lon_axis = _axes(lat_grid)
    lat = np.asarray(lat_grid, dtype=float)
    lon = np.asarray(lon_grid, dtype=float)

    dlat, dlon = _velocity_degrees_per_hour(
        lat, current_u, current_v, wind_u, wind_v, lat_axis, lon_axis
    )

    # Backtrace the departure point. A single-day step is small enough for the
    # prototype grid; splitting into 6-hour substeps improves stability.
    remaining = float(hours)
    result = base.copy()
    while remaining > 1e-9:
        dt = min(6.0, remaining)
        # Recompute forcing at the current grid cells. This is a conservative
        # first-order semi-Lagrangian step, not a claim of full sea-ice physics.
        dep_lat = lat - dlat * dt
        dep_lon = lon - dlon * dt
        sampled = _nearest_sample(result, lat_axis, lon_axis, dep_lat, dep_lon)
        result = np.clip(sampled, 0.0, 1.0)
        remaining -= dt
    return result


def _seasonal_baseline(
    concentration: np.ndarray,
    day_of_year: int,
    lat_grid: np.ndarray,
    horizon_day: int,
) -> np.ndarray:
    base = np.asarray(concentration, dtype=float)
    lat_axis, _ = _axes(lat_grid)
    lat_norm = (lat_axis - lat_axis.min()) / max(1e-9, lat_axis.max() - lat_axis.min())
    # Seasonal correction is intentionally modest: it must not overwhelm the
    # observed state when persistence is already the stronger signal.
    amp_axis = 0.035 + 0.030 * (1.0 - lat_norm)
    amp = np.repeat(amp_axis[:, None], base.shape[1], axis=1)
    phase = 2.0 * np.pi * (float(day_of_year) - 60.0) / 365.25
    shift = amp * np.sin(phase + float(horizon_day) / 18.0)
    return np.clip(base + shift, 0.0, 1.0)


def forecast_concentration(
    concentration,
    day_of_year,
    lat_grid,
    horizon_days=3,
    current_u=None,
    current_v=None,
    wind_u=None,
    wind_v=None,
    lon_grid=None,
):
    """Return a 1..7 day hybrid sea-ice concentration forecast.

    With real environmental forcing, the forecast uses conservative
    semi-Lagrangian advection blended with persistence and a small seasonal
    correction. Without forcing it falls back to the same transparent
    persistence/seasonal model used for offline and historical validation.
    """
    h = max(1, min(7, int(horizon_days)))
    base = np.clip(np.asarray(concentration, dtype=float), 0.0, 1.0)
    lat_grid = np.asarray(lat_grid, dtype=float)
    if lon_grid is None:
        lon_grid = np.linspace(-180.0, 180.0, base.shape[1])[None, :].repeat(base.shape[0], axis=0)
    else:
        lon_grid = np.asarray(lon_grid, dtype=float)

    forcing_available = all(x is not None for x in (current_u, current_v))
    if forcing_available:
        try:
            cu = np.asarray(current_u, dtype=float)
            cv = np.asarray(current_v, dtype=float)
            forcing_available = (
                cu.shape == base.shape
                and cv.shape == base.shape
                and np.isfinite(cu).any()
                and np.isfinite(cv).any()
                and float(np.nanmax(np.abs(cu))) + float(np.nanmax(np.abs(cv))) > 1e-8
            )
        except Exception:
            forcing_available = False

    if forcing_available:
        physics_fields = []
        current = base.copy()
        for d in range(1, h + 1):
            advected = _semi_lagrangian_step(
                current,
                lat_grid,
                lon_grid,
                cu,
                cv,
                None if wind_u is None else np.asarray(wind_u, dtype=float),
                None if wind_v is None else np.asarray(wind_v, dtype=float),
                24.0,
            )
            seasonal = _seasonal_baseline(base, int(day_of_year), lat_grid, d)
            # Forecast uncertainty grows with lead time; therefore the blend
            # becomes slightly more conservative at longer horizons.
            physics_weight = max(0.35, 0.72 - 0.055 * (d - 1))
            persistence_weight = 0.18
            seasonal_weight = max(0.10, 1.0 - physics_weight - persistence_weight)
            current = np.clip(
                physics_weight * advected
                + persistence_weight * base
                + seasonal_weight * seasonal,
                0.0,
                1.0,
            )
            physics_fields.append(current.copy())
        return np.stack(physics_fields)

    # Offline/historical path. Keep persistence dominant so the seasonal term
    # remains a correction rather than an artificial source of drift.
    out = []
    for d in range(1, h + 1):
        seasonal = _seasonal_baseline(base, int(day_of_year), lat_grid, d)
        seasonal_weight = max(0.05, 0.16 - 0.015 * (d - 1))
        out.append(np.clip((1.0 - seasonal_weight) * base + seasonal_weight * seasonal, 0.0, 1.0))
    return np.stack(out)
