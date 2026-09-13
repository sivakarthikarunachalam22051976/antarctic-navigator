"""Validate a generated navigator_bundle.json before publishing it."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "backend" / "data" / "real" / "navigator_bundle.json"


def validate(path: str | Path = BUNDLE) -> dict[str, object]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Bundle not found: {path}")

    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)

    required = {
        "meta",
        "lat_grid",
        "lon_grid",
        "concentration",
        "current_u",
        "current_v",
        "wind_u",
        "wind_v",
        "navigable_mask",
        "icebergs",
    }
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"Bundle is missing required fields: {missing}")

    concentration = np.asarray(data["concentration"], dtype=float)
    shape = concentration.shape
    if concentration.ndim != 2 or any(d == 0 for d in shape):
        raise ValueError(f"Invalid concentration shape: {shape}")

    for name in (
        "lat_grid",
        "lon_grid",
        "current_u",
        "current_v",
        "wind_u",
        "wind_v",
    ):
        arr = np.asarray(data[name], dtype=float)
        if arr.shape != shape:
            raise ValueError(
                f"{name} shape {arr.shape} does not match concentration {shape}"
            )
        if not np.isfinite(arr).all():
            raise ValueError(f"{name} contains non-finite values")

    mask = np.asarray(data["navigable_mask"], dtype=bool)
    if mask.shape != shape:
        raise ValueError("navigable_mask shape does not match concentration")

    if np.nanmin(concentration) < 0 or np.nanmax(concentration) > 1:
        raise ValueError("Sea-ice concentration must be in [0, 1]")

    if not isinstance(data["icebergs"], list):
        raise ValueError("icebergs must be a list")

    required_iceberg_fields = {"id", "lat", "lon", "length_km", "width_km"}
    for index, iceberg in enumerate(data["icebergs"]):
        missing_iceberg = sorted(required_iceberg_fields - set(iceberg))
        if missing_iceberg:
            raise ValueError(
                f"Iceberg {index} is missing fields: {missing_iceberg}"
            )
        for key in ("lat", "lon", "length_km", "width_km"):
            value = float(iceberg[key])
            if not math.isfinite(value):
                raise ValueError(f"Iceberg {index} field {key} is not finite")

    meta = data["meta"]
    if not isinstance(meta, dict):
        raise ValueError("meta must be an object")
    if not meta.get("source"):
        raise ValueError("meta.source is required")
    if not meta.get("observation_date"):
        raise ValueError("meta.observation_date is required")
    if not meta.get("bundle_generated_at_utc"):
        raise ValueError("meta.bundle_generated_at_utc is required")

    # If a forcing source is present, its provenance timestamps must also be
    # present. This prevents the UI from claiming a source is loaded while
    # silently showing an unknown observation/analysis date.
    if meta.get("current_source"):
        if not meta.get("current_observation_date"):
            raise ValueError("current_observation_date is required when OSCAR is loaded")
        if not meta.get("current_retrieved_at_utc"):
            raise ValueError("current_retrieved_at_utc is required when OSCAR is loaded")

    if meta.get("wind_source"):
        if not meta.get("wind_observation_date"):
            raise ValueError("wind_observation_date is required when ERA5 is loaded")
        if not meta.get("wind_retrieved_at_utc"):
            raise ValueError("wind_retrieved_at_utc is required when ERA5 is loaded")

    # The real bundle used for the prototype should produce a route between
    # India's two Antarctic stations under the current risk-weighted router.
    route_check = "not_run"
    if str(meta.get("dataset_kind", "")).startswith("real_"):
        import sys
        sys.path.insert(0, str(ROOT / "backend"))
        import main as api  # noqa: E402
        from config import INDIAN_STATIONS  # noqa: E402
        from models.router import find_route  # noqa: E402
        from models.seaice_forecast import forecast_concentration  # noqa: E402

        api.USE_REAL = True
        api._dataset = None
        dataset = api.get_dataset()
        forecast = forecast_concentration(
            dataset["concentration"],
            int(dataset["meta"].get("day_of_year", 1)),
            dataset["lat_grid"],
            3,
        )
        start = api._route_cell_for_point(**INDIAN_STATIONS["Maitri"])[:2]
        goal = api._route_cell_for_point(**INDIAN_STATIONS["Bharati"])[:2]
        risk = api.iceberg_risk_grid(
            api.project_icebergs(dataset["icebergs"], 72),
            forecast[-1].shape,
        )
        _, _ = find_route(
            forecast[-1],
            tuple(map(int, start)),
            tuple(map(int, goal)),
            risk,
            "standard",
            dataset["navigable_mask"],
        )
        route_check = "Maitri-to-Bharati ok"

    return {
        "status": "ok",
        "bundle": str(path),
        "shape": shape,
        "icebergs": len(data["icebergs"]),
        "dataset_kind": meta.get("dataset_kind"),
        "observation_date": meta.get("observation_date"),
        "bundle_generated_at_utc": meta.get("bundle_generated_at_utc"),
        "sea_ice_retrieved_at_utc": meta.get("sea_ice_retrieved_at_utc", ""),
        "iceberg_observation_date": meta.get("iceberg_observation_date", ""),
        "iceberg_retrieved_at_utc": meta.get("iceberg_retrieved_at_utc", ""),
        "current_observation_date": meta.get("current_observation_date", ""),
        "current_retrieved_at_utc": meta.get("current_retrieved_at_utc", ""),
        "wind_observation_date": meta.get("wind_observation_date", ""),
        "wind_retrieved_at_utc": meta.get("wind_retrieved_at_utc", ""),
        "environmental_forcing": meta.get("environmental_forcing", ""),
        "route_check": route_check,
    }


if __name__ == "__main__":
    print(validate())
