"""Stress-test route decisions against iceberg-position uncertainty.

This test uses the current real navigator bundle and deliberately perturbs each
projected iceberg radially by +/- configured distances. It does NOT claim a
statistical confidence interval; it is a deterministic route-sensitivity test.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
os.environ.setdefault("USE_REAL_DATA", "1")
os.environ.setdefault("ALLOW_SYNTHETIC_FALLBACK", "0")

import sys
sys.path.insert(0, str(BACKEND))

import main as api
from config import INDIAN_STATIONS, latlon_to_rc
from models.router import find_route
from models.seaice_forecast import forecast_concentration


def move_km(lat: float, lon: float, distance_km: float, bearing_deg: float) -> tuple[float, float]:
    br = math.radians(bearing_deg)
    dlat = distance_km * math.cos(br) / 111.32
    dlon = distance_km * math.sin(br) / max(10.0, 111.32 * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


def shifted_projection(projected: list[dict[str, Any]], distance_km: float, bearing_deg: float) -> list[dict[str, Any]]:
    shifted = []
    for item in projected:
        copy = dict(item)
        lat, lon = move_km(float(item["projected_lat"]), float(item["projected_lon"]), distance_km, bearing_deg)
        copy["projected_lat"] = lat
        copy["projected_lon"] = lon
        copy["ensemble"] = []
        shifted.append(copy)
    return shifted


def path_risk(path: list[tuple[int, int]], risk: np.ndarray) -> dict[str, float]:
    vals = np.asarray([risk[r, c] for r, c in path], dtype=float)
    return {
        "mean_iceberg_risk": float(vals.mean()) if len(vals) else 0.0,
        "max_iceberg_risk": float(vals.max()) if len(vals) else 0.0,
        "high_risk_fraction": float(np.mean(vals >= 0.75)) if len(vals) else 0.0,
    }


def run(horizon_days: int = 3, vessel_profile: str = "standard") -> dict[str, Any]:
    # Validation must be independent of whatever shell flags the user currently has.
    # Force the API module itself into real-data mode after import; setdefault() alone
    # cannot override an already-imported module state.
    api.USE_REAL = True
    api.ALLOW_SYNTHETIC_FALLBACK = False
    api._dataset = None
    if not api.REAL.exists():
        raise RuntimeError(f"Real navigator bundle not found: {api.REAL}")
    dataset = api.get_dataset()
    if not bool(dataset["meta"].get("real_data_active")):
        raise RuntimeError("Route robustness requires the real navigator bundle; synthetic fallback is disabled.")

    start = api._route_cell_for_point(INDIAN_STATIONS["Maitri"]["lat"], INDIAN_STATIONS["Maitri"]["lon"])
    goal = api._route_cell_for_point(INDIAN_STATIONS["Bharati"]["lat"], INDIAN_STATIONS["Bharati"]["lon"])
    start_rc = (start[0], start[1])
    goal_rc = (goal[0], goal[1])

    forecast = forecast_concentration(
        dataset["concentration"],
        int(dataset["meta"].get("day_of_year", 1)),
        dataset["lat_grid"],
        horizon_days,
        current_u=dataset.get("current_u"),
        current_v=dataset.get("current_v"),
        wind_u=dataset.get("wind_u"),
        wind_v=dataset.get("wind_v"),
        lon_grid=dataset.get("lon_grid"),
    )
    target = forecast[horizon_days - 1]
    projected = api.project_icebergs(dataset["icebergs"], horizon_days * 24)
    base_risk = api.iceberg_risk_grid(projected, target.shape)

    base_path, base_cost = find_route(
        target, start_rc, goal_rc, base_risk, vessel_profile, dataset["navigable_mask"], objective="balanced"
    )
    base_metrics = api._route_metrics(
        base_path, base_cost, target, base_risk, horizon_days, vessel_profile,
        dataset["meta"], start[0], start[1], goal[0], goal[1], start[2], goal[2]
    )

    scenarios = []
    bearings = tuple(range(0, 360, 45))
    for distance in (5.0, 10.0, 20.0):
        max_risk = 0.0
        max_mean = 0.0
        successful = 0
        reroute_risk_values = []
        baseline_path_stays_below_high = 0
        for bearing in bearings:
            shifted = shifted_projection(projected, distance, float(bearing))
            risk = api.iceberg_risk_grid(shifted, target.shape)
            baseline_path_metrics = path_risk(base_path, risk)
            max_risk = max(max_risk, baseline_path_metrics["max_iceberg_risk"])
            max_mean = max(max_mean, baseline_path_metrics["mean_iceberg_risk"])
            if baseline_path_metrics["max_iceberg_risk"] < 0.75:
                baseline_path_stays_below_high += 1
            try:
                reroute_path, reroute_cost = find_route(
                    target, start_rc, goal_rc, risk, vessel_profile, dataset["navigable_mask"], objective="balanced"
                )
                successful += 1
                reroute_metrics = api._route_metrics(
                    reroute_path, reroute_cost, target, risk, horizon_days, vessel_profile,
                    dataset["meta"], start[0], start[1], goal[0], goal[1], start[2], goal[2]
                )
                reroute_risk_values.append(reroute_metrics["max_iceberg_risk"])
            except ValueError:
                pass
        scenarios.append({
            "perturbation_km": distance,
            "directions_tested": len(bearings),
            "reroute_success_rate": successful / len(bearings),
            "baseline_recommended_path_high_risk_fraction": baseline_path_stays_below_high / len(bearings),
            "worst_case_baseline_path_max_iceberg_risk": max_risk,
            "worst_case_baseline_path_mean_iceberg_risk": max_mean,
            "worst_case_rerouted_max_iceberg_risk": max(reroute_risk_values) if reroute_risk_values else None,
        })

    return {
        "status": "completed",
        "method": "Deterministic radial iceberg-position sensitivity test; 8 bearings per perturbation.",
        "not_a_confidence_interval": True,
        "data_mode": dataset["meta"].get("dataset_kind"),
        "sea_ice_observation_date": dataset["meta"].get("observation_date"),
        "iceberg_observation_date": dataset["meta"].get("iceberg_observation_date"),
        "horizon_days": horizon_days,
        "vessel_profile": vessel_profile,
        "baseline": {
            "distance_km": base_metrics["distance_km"],
            "risk_score": base_metrics["risk_score"],
            "max_iceberg_risk": base_metrics["max_iceberg_risk"],
            "exposure_band": base_metrics["exposure_band"],
            "waypoints": base_metrics["waypoints"],
        },
        "scenarios": scenarios,
        "interpretation": "Robustness is stronger when rerouting remains feasible and the baseline path does not enter high iceberg-risk cells under the tested perturbations.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=3, choices=range(1, 8))
    parser.add_argument("--vessel", default="standard")
    parser.add_argument("--output", default="validation/route_robustness.json")
    args = parser.parse_args()
    result = run(args.horizon, args.vessel)
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
