"""Deterministic local integrity checks for the Antarctic Navigator."""
from __future__ import annotations

import compileall
import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
TEST_DATA = BACKEND / "data" / "test" / "usnic_sample.csv"

sys.path.insert(0, str(BACKEND))


def _test_environmental_regridding() -> None:
    """Use tiny NetCDF3 fixtures so the regridding helpers are exercised."""
    from data.convert_nsidc_bundle import _load_latlon_uv, _reproject_latlon
    from config import latlon_grids

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        lat = np.array([-75.0, -70.0, -65.0])
        lon = np.array([0.0, 30.0, 60.0, 90.0])

        # OSCAR-like fields.
        time = np.array(["2026-09-05T00:00:00"], dtype="datetime64[ns]")
        u = np.ones((1, 3, 4), dtype=float) * 0.20
        v = np.ones((1, 3, 4), dtype=float) * -0.10
        oscar = xr.Dataset(
            {
                "u": (("time", "latitude", "longitude"), u),
                "v": (("time", "latitude", "longitude"), v),
            },
            coords={
                "time": time,
                "latitude": lat,
                "longitude": lon,
            },
        )
        oscar_path = tmp_path / "oscar.nc"
        oscar.to_netcdf(oscar_path, engine="scipy")

        loaded_lat, loaded_lon, loaded_u, loaded_v, observed_date = _load_latlon_uv(
            oscar_path,
            ("u",),
            ("v",),
        )
        assert observed_date == "2026-09-05"
        assert loaded_u.shape == (3, 4)
        assert loaded_v.shape == (3, 4)

        target_lat, target_lon = latlon_grids()
        out_u = _reproject_latlon(
            loaded_u,
            loaded_lon,
            loaded_lat,
            target_lat,
            target_lon,
        )
        out_v = _reproject_latlon(
            loaded_v,
            loaded_lon,
            loaded_lat,
            target_lat,
            target_lon,
        )
        assert out_u.shape == target_lat.shape
        assert out_v.shape == target_lat.shape
        assert np.isfinite(out_u).any()
        assert np.isfinite(out_v).any()

        # Exercise CF-style numeric time decoding used by real OSCAR/ERA5
        # files (for example, "days since 1990-1-1").
        numeric = xr.Dataset(
            {
                "u": (("time", "latitude", "longitude"), u),
                "v": (("time", "latitude", "longitude"), v),
            },
            coords={
                "time": ("time", np.array([13433.0]), {"units": "days since 1990-01-01", "calendar": "standard"}),
                "latitude": lat,
                "longitude": lon,
            },
        )
        numeric_path = tmp_path / "oscar_numeric.nc"
        numeric.to_netcdf(numeric_path, engine="scipy")
        _, _, _, _, numeric_date = _load_latlon_uv(
            numeric_path,
            ("u",),
            ("v",),
        )
        assert numeric_date == "2026-10-12"

        # Reproduce the OSCAR file layout that caused the original production
        # failure: the field is stored as (longitude, latitude), not
        # (latitude, longitude). The loader must normalize this automatically.
        oscar_reversed = xr.Dataset(
            {
                "u": (("longitude", "latitude"), u[0].T),
                "v": (("longitude", "latitude"), v[0].T),
            },
            coords={
                "latitude": lat,
                "longitude": lon,
            },
        )
        reversed_path = tmp_path / "oscar_reversed.nc"
        oscar_reversed.to_netcdf(reversed_path, engine="scipy")

        _, _, reversed_u, reversed_v, _ = _load_latlon_uv(
            reversed_path,
            ("u",),
            ("v",),
        )
        assert reversed_u.shape == (3, 4)
        assert reversed_v.shape == (3, 4)
        assert np.allclose(reversed_u, u[0])
        assert np.allclose(reversed_v, v[0])

        # ERA5-like fields.
        era = xr.Dataset(
            {
                "u10": (("time", "latitude", "longitude"), u * 10),
                "v10": (("time", "latitude", "longitude"), v * 10),
            },
            coords={
                "time": time,
                "latitude": lat[::-1],
                "longitude": lon,
            },
        )
        # Reverse the latitude dimension consistently with coordinates.
        era = era.sortby("latitude")
        era_path = tmp_path / "era5.nc"
        era.to_netcdf(era_path, engine="scipy")

        loaded_lat, loaded_lon, loaded_u, loaded_v, _ = _load_latlon_uv(
            era_path,
            ("u10",),
            ("v10",),
        )
        assert loaded_u.shape == (3, 4)
        assert np.isfinite(loaded_u).any()


def _validate_shipped_real_bundle() -> None:
    """Verify the packaged real bundle is genuinely source-derived."""
    real_bundle = BACKEND / "data" / "real" / "navigator_bundle.json"
    if not real_bundle.exists():
        raise SystemExit("Packaged real navigator bundle is missing.")
    with real_bundle.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    meta = payload.get("meta", {})
    required = {
        "real_seaice_usnic_icebergs",
        "NOAA/NSIDC G10016 Version 4",
        "U.S. National Ice Center (USNIC)",
        "NASA/JPL PO.DAAC OSCAR NRT V2.0",
        "Copernicus/ECMWF ERA5",
    }
    observed = {
        str(meta.get("dataset_kind", "")),
        str(meta.get("source", "")),
        str(meta.get("iceberg_source", "")),
        str(meta.get("current_source", "")),
        str(meta.get("wind_source", "")),
    }
    if not required.issubset(observed):
        raise SystemExit(f"Real bundle provenance check failed: {required - observed}")
    if not payload.get("concentration") or not payload.get("icebergs"):
        raise SystemExit("Real bundle appears incomplete.")
    if len(payload["concentration"]) != 60 or len(payload["concentration"][0]) != 180:
        raise SystemExit("Real bundle grid shape is not the expected 60x180.")
    print("REAL_BUNDLE_OK", {
        "sea_ice_date": meta.get("observation_date"),
        "iceberg_date": meta.get("iceberg_observation_date"),
        "current_date": meta.get("current_observation_date"),
        "wind_date": meta.get("wind_observation_date"),
        "icebergs": len(payload.get("icebergs", [])),
    })


def main() -> None:
    _validate_shipped_real_bundle()
    if not compileall.compile_dir(
        str(BACKEND),
        quiet=1,
    ):
        raise SystemExit("Python compilation check failed.")

    import main as api
    from config import INDIAN_STATIONS, latlon_to_rc
    from data.integrate_usnic_icebergs import parse_usnic_csv
    from models.router import find_route
    from models.seaice_forecast import forecast_concentration
    from models.polar_intelligence import attainable_speed_kn, polar_safety_screen, polar_stereographic_xy

    # self_check.py is a deterministic software-integrity test. It must not
    # change behavior just because the user's shell currently has
    # USE_REAL_DATA=1 for running the live application.
    #
    # Real-data validation belongs to validate_real_bundle.py. For this smoke
    # test, deliberately force the bundled synthetic dataset so station
    # coordinates remain deterministic and are not affected by a real
    # sea/land navigability mask.
    api.USE_REAL = False
    api._dataset = None

    dataset = api.get_dataset()
    get_dataset = api.get_dataset
    iceberg_risk_grid = api.iceberg_risk_grid
    project_icebergs = api.project_icebergs
    forecast = forecast_concentration(
        dataset["concentration"],
        int(dataset["meta"].get("day_of_year", 1)),
        dataset["lat_grid"],
        3,
    )
    projected = project_icebergs(
        dataset["icebergs"],
        72,
    )
    risk = iceberg_risk_grid(
        projected,
        forecast[-1].shape,
    )

    start = latlon_to_rc(
        INDIAN_STATIONS["Maitri"]["lat"],
        INDIAN_STATIONS["Maitri"]["lon"],
    )
    goal = latlon_to_rc(
        INDIAN_STATIONS["Bharati"]["lat"],
        INDIAN_STATIONS["Bharati"]["lon"],
    )

    path, cost = find_route(
        forecast[-1],
        start,
        goal,
        risk,
        "standard",
        dataset["navigable_mask"],
    )

    if not path or not np.isfinite(cost):
        raise SystemExit("Route smoke test failed.")

    # Verify the mission-aware decision layer returns all three explainable
    # route lenses and a valid recommendation without changing the underlying
    # deterministic synthetic routing test.
    alternatives = api.route(
        INDIAN_STATIONS["Maitri"]["lat"],
        INDIAN_STATIONS["Maitri"]["lon"],
        INDIAN_STATIONS["Bharati"]["lat"],
        INDIAN_STATIONS["Bharati"]["lon"],
        3,
        "standard",
        "resupply",
        "balanced",
        "medium",
        48,
    )
    route_ids = {item["id"] for item in alternatives["alternatives"]}
    if route_ids != {"A", "B", "C"}:
        raise SystemExit(
            f"Mission-aware routing expected A/B/C candidates, got {route_ids}."
        )
    if alternatives["recommendation"]["route_id"] not in route_ids:
        raise SystemExit("Mission-aware routing recommendation is invalid.")
    if alternatives.get("geometry", {}).get("projection") != "EPSG:3031":
        raise SystemExit("Polar geometry projection marker missing.")
    if "RK4" not in alternatives.get("intelligence", {}).get("iceberg_trajectory", ""):
        raise SystemExit("RK4 trajectory marker missing.")
    if attainable_speed_kn("ice_capable", 0.20) <= 0:
        raise SystemExit("Vessel performance model failed.")
    screen = polar_safety_screen("ice_capable", 0.50)
    if screen["status"] not in {"PASS", "REVIEW", "BLOCK"}:
        raise SystemExit("Polar safety screening failed.")
    x, y = polar_stereographic_xy(-70.0, 20.0)
    if not np.isfinite([x, y]).all():
        raise SystemExit("EPSG:3031 projection failed.")

    items, meta = parse_usnic_csv(TEST_DATA)
    if len(items) != 2:
        raise SystemExit(
            f"USNIC parser test expected 2 records, got {len(items)}."
        )
    if meta["latest_source_update"] != "2026-06-25":
        raise SystemExit("USNIC date-normalisation test failed.")

    with (BACKEND / "data" / "sample" / "synthetic_dataset.json").open(
        encoding="utf-8"
    ) as handle:
        json.load(handle)

    _test_environmental_regridding()

    # Frontend integrity checks: the shipped UI must contain the same
    # mission-aware A/B/C route workflow as the backend API. This prevents
    # accidentally packaging an older single-route frontend.
    frontend_app = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    frontend_html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    frontend_css = (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")
    required_frontend_markers = (
        'A: { color:',
        'B: { color:',
        'C: { color:',
        '3 candidate routes evaluated',
        'Recommended Route',
        'Why selected?',
        'class="freshness-table"',
        'Voyage intelligence',
        'RK4 + ensemble',
        'EPSG:3031',
        'Polar safety screening',
        'Closest projected iceberg',
        'REAL DATA ACTIVE',
    )
    combined_frontend = frontend_app + frontend_html + frontend_css
    missing_frontend = [marker for marker in required_frontend_markers if marker not in combined_frontend]
    if missing_frontend:
        raise SystemExit(f"Frontend mission-aware UI markers missing: {missing_frontend}")

    print(
        "SELF_CHECK_OK",
        {
            "route_waypoints": len(path),
            "route_cost": round(cost, 3),
            "synthetic_icebergs": len(dataset["icebergs"]),
            "usnic_fixture_records": len(items),
            "environmental_regrid": "ok",
            "mission_aware_routes": sorted(route_ids),
        },
    )


if __name__ == "__main__":
    main()
