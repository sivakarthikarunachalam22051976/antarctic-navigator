"""Historical sea-ice validation with strict calendar-date matching.

This evaluates the transparent no-forcing historical forecast component used by
this validator. It does not claim validation of the production forcing-driven
hybrid unless historical current/wind fields are explicitly supplied.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from models.seaice_forecast import forecast_concentration


def open_concentration(path: Path) -> tuple[np.ndarray, str]:
    ds = xr.open_dataset(path, decode_times=True)
    try:
        candidates = ["cdr_seaice_conc", "seaice_conc", "concentration", "conc", "nsidc"]
        name = next((n for n in candidates if n in ds.data_vars), None)
        if name is None:
            for n, da in ds.data_vars.items():
                if da.ndim >= 2 and np.issubdtype(da.dtype, np.number):
                    name = n; break
        if name is None:
            raise ValueError(f"No numeric concentration field in {path.name}")
        arr = np.asarray(ds[name].squeeze().values, dtype=float)
        finite = arr[np.isfinite(arr)]
        if len(finite) and np.nanpercentile(finite, 95) > 1.5:
            arr = arr / 100.0
        arr = np.clip(arr, 0.0, 1.0)
        times = ds.indexes.get("time")
        if times is not None and len(times):
            
            t0 = times[0]
            obs_date = (t0.date().isoformat() if hasattr(t0, "date") else str(t0)[:10])
        else:
            obs_date = path.stem
        return arr, obs_date
    finally:
        ds.close()


def metrics(pred: np.ndarray, obs: np.ndarray) -> dict[str, Any]:
    mask = np.isfinite(pred) & np.isfinite(obs)
    p = pred[mask]; o = obs[mask]
    err = p-o
    if len(p) == 0:
        return {"samples": 0}
    corr = float(np.corrcoef(p, o)[0,1]) if len(p) > 1 and np.std(p) > 0 and np.std(o) > 0 else None
    return {"samples": int(len(p)), "mae": float(np.mean(np.abs(err))), "rmse": float(np.sqrt(np.mean(err**2))), "bias": float(np.mean(err)), "correlation": corr}


def aggregate(rows):
    valid = [r for r in rows if r.get("samples", 0)]
    if not valid:
        return {"windows": 0}
    out = {"windows": len(valid)}
    for key in ("mae", "rmse", "bias", "correlation"):
        vals = [r[key] for r in valid if r.get(key) is not None]
        if vals: out[key] = float(np.mean(vals))
    out["grid_samples_per_window"] = int(np.median([r["samples"] for r in valid]))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--output", default="validation/seaice_validation.json")
    parser.add_argument("--max-horizon", type=int, default=7)
    args = parser.parse_args()
    files = sorted(
    path for path in Path(args.data_dir).rglob("*.nc")
    if path.is_file()
)
    if len(files) < 2:
        raise SystemExit("Need at least two historical NSIDC NetCDF files.")

    observations = []
    for f in files:
        try:
            arr, obs_date = open_concentration(f)
            observations.append((obs_date, arr, f))
        except Exception as exc:
            print(f"Skipping {f.name}: {exc}")
    observations.sort(key=lambda x: x[0])
    if len(observations) < 2:
        raise SystemExit("No usable historical NSIDC concentration files found.")

    # Exact-date map. Duplicate observation dates are rejected rather than silently overwritten.
    by_date = {}
    duplicate_dates = []
    for item in observations:
        if item[0] in by_date:
            duplicate_dates.append(item[0])
        else:
            by_date[item[0]] = item
    observations = list(by_date.values())
    available_dates = {date.fromisoformat(x[0]) for x in observations if len(x[0]) == 10}
    min_date, max_date = min(available_dates), max(available_dates)
    expected = {min_date + timedelta(days=i) for i in range((max_date-min_date).days + 1)}
    missing_dates = sorted(expected - available_dates)

    lat_grid = np.linspace(-90, -50, observations[0][1].shape[0])[:, None]
    lat_grid = np.repeat(lat_grid, observations[0][1].shape[1], axis=1)

    model_scores = {str(h): [] for h in range(1, args.max_horizon+1)}
    persistence_scores = {str(h): [] for h in range(1, args.max_horizon+1)}
    skipped_gap_windows = {str(h): 0 for h in range(1, args.max_horizon+1)}

    for date_text, base, _ in observations:
        try:
            start = date.fromisoformat(date_text)
            doy = start.timetuple().tm_yday
        except Exception:
            continue
        forecast = forecast_concentration(base, doy, lat_grid, args.max_horizon)
        for h in range(1, args.max_horizon+1):
            target_date = (start + timedelta(days=h)).isoformat()
            target = by_date.get(target_date)
            if target is None:
                if start + timedelta(days=h) <= max_date:
                    skipped_gap_windows[str(h)] += 1
                continue
            obs = target[1]
            model_scores[str(h)].append(metrics(forecast[h-1], obs))
            persistence_scores[str(h)].append(metrics(base, obs))

    result = {
        "status": "completed",
        "source": "Historical NSIDC daily concentration files supplied by user",
        "forecast_model": "Statistical persistence + seasonal baseline (no historical current/wind forcing supplied to this validator)",
        "comparison_baseline": "Pure persistence",
        "full_forcing_model_historical_validation": False,
        "metrics_are_not_operational_skill": True,
        "strict_time_matching": True,
        "files_found": len(files),
        "files_used": len(observations),
        "duplicate_dates": sorted(set(duplicate_dates)),
        "missing_dates": [d.isoformat() for d in missing_dates],
        "missing_day_count": len(missing_dates),
        "skipped_gap_windows": skipped_gap_windows,
        "model": {h: aggregate(rows) for h, rows in model_scores.items()},
        "persistence": {h: aggregate(rows) for h, rows in persistence_scores.items()},
    }
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
