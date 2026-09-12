"""Build the compact Antarctic Navigator bundle from current source data.

Inputs (all under backend/data/real/raw/):
- NSIDC G10016 V4 South Polar daily NetCDF (required for real sea ice).
- USNIC Antarctic iceberg CSV (optional but recommended/current).
- Optional OSCAR NRT current NetCDF under environmental/oscar/.
- Optional ERA5 10-m wind NetCDF under environmental/era5/.

The output is backend/data/real/navigator_bundle.json. Raw source files are
kept out of Git; the compact bundle is the file used by the SIH prototype.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from pyproj import Transformer
from scipy.interpolate import RegularGridInterpolator

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from config import latlon_grids  # noqa: E402
from data.integrate_usnic_icebergs import parse_usnic_csv  # noqa: E402

REAL_DIR = BACKEND_DIR / "data" / "real"
RAW_DIR = REAL_DIR / "raw"
OUT = REAL_DIR / "navigator_bundle.json"
ENV_DIR = RAW_DIR / "environmental"
OSCAR_DIR = ENV_DIR / "oscar"
ERA5_DIR = ENV_DIR / "era5"

NSIDC_VERSION = "4"
NSIDC_SHORT_NAME = "G10016"


def _file_retrieved_at_utc(path: Path) -> str:
    """Use the local file timestamp as the ingestion/retrieval timestamp.

    This is intentionally separate from the source observation/update date.
    The bundle stores both so the UI can tell users what the data represents
    and when this application last ingested the source file.
    """
    return datetime.fromtimestamp(
        path.stat().st_mtime,
        tz=timezone.utc,
    ).isoformat()


def _pick_variable(
    ds: xr.Dataset,
    preferred: tuple[str, ...],
    contains: tuple[str, ...],
) -> xr.DataArray:
    for name in preferred:
        if name in ds.data_vars:
            return ds[name]

    for name, value in ds.data_vars.items():
        lower = name.lower()
        if all(token in lower for token in contains):
            return value

    raise ValueError(
        f"Could not find a variable matching {preferred or contains}. "
        f"Available variables: {list(ds.data_vars)}"
    )


def _pick_concentration_variable(ds: xr.Dataset) -> xr.DataArray:
    return _pick_variable(
        ds,
        (
            "cdr_seaice_conc",
            "seaice_conc_cdr",
            "nsidc_south",
            "seaice_conc",
        ),
        ("seaice", "conc"),
    )


def _to_2d(da: xr.DataArray) -> xr.DataArray:
    da = da.squeeze(drop=True)

    if "y" in da.dims and "x" in da.dims:
        return da.transpose("y", "x")

    while da.ndim > 2:
        da = da.isel({da.dims[0]: -1})

    if da.ndim != 2:
        raise ValueError(
            f"Expected a 2D field after squeezing; got dimensions {da.dims}."
        )

    return da


def _coord_name(
    ds: xr.Dataset,
    candidates: tuple[str, ...],
) -> str:
    available = {name.lower(): name for name in ds.coords}
    available.update({name.lower(): name for name in ds.variables})

    for candidate in candidates:
        if candidate.lower() in available:
            return available[candidate.lower()]

    raise ValueError(
        f"Could not find a coordinate named one of {candidates}. "
        f"Available coordinates/variables: {list(available.values())}"
    )


def _normalise_lon(
    lon: np.ndarray,
) -> np.ndarray:
    lon = np.asarray(lon, dtype=float)
    # Convert 0..360 grids to -180..180 for stable interpolation.
    converted = ((lon + 180.0) % 360.0) - 180.0
    # Preserve a conventional 180 endpoint when it is present.
    return converted


def _sort_regular_grid(
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    values = np.asarray(values, dtype=float)

    x_order = np.argsort(x)
    y_order = np.argsort(y)

    x = x[x_order]
    y = y[y_order]
    values = values[np.ix_(y_order, x_order)]

    # A longitude array that crossed the dateline can contain duplicates after
    # normalisation. Collapse duplicate x coordinates by averaging their values.
    unique_x, inverse = np.unique(x, return_inverse=True)
    if len(unique_x) != len(x):
        collapsed = np.full(
            (len(y), len(unique_x)),
            np.nan,
            dtype=float,
        )
        counts = np.zeros(len(unique_x), dtype=int)
        for idx, target_idx in enumerate(inverse):
            column = values[:, idx]
            mask = np.isfinite(column)
            collapsed[mask, target_idx] = np.nan_to_num(
                collapsed[mask, target_idx],
                nan=0.0,
            ) + column[mask]
            counts[target_idx] += 1
        for idx, count in enumerate(counts):
            if count > 1:
                collapsed[:, idx] /= count
        values = collapsed
        x = unique_x

    return x, y, values


def _reproject_latlon(
    values: np.ndarray,
    source_lon: np.ndarray,
    source_lat: np.ndarray,
    target_lat: np.ndarray,
    target_lon: np.ndarray,
    fill_value: float = np.nan,
    method: str = "linear",
) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    source_lon, source_lat, values = _sort_regular_grid(
        source_lon,
        source_lat,
        values,
    )

    interpolator = RegularGridInterpolator(
        (source_lat, source_lon),
        values,
        method=method,
        bounds_error=False,
        fill_value=fill_value,
    )

    points = np.column_stack(
        [target_lat.ravel(), target_lon.ravel()]
    )
    return interpolator(points).reshape(target_lat.shape)


def _reproject_polar(
    values: np.ndarray,
    source_x: np.ndarray,
    source_y: np.ndarray,
    target_lat: np.ndarray,
    target_lon: np.ndarray,
    method: str = "linear",
) -> np.ndarray:
    transformer = Transformer.from_crs(
        "EPSG:4326",
        "EPSG:3412",
        always_xy=True,
    )
    target_x, target_y = transformer.transform(
        target_lon,
        target_lat,
    )

    source_x, source_y, values = _sort_regular_grid(
        source_x,
        source_y,
        values,
    )

    interpolator = RegularGridInterpolator(
        (source_y, source_x),
        values,
        method=method,
        bounds_error=False,
        fill_value=np.nan,
    )

    sample_points = np.column_stack(
        [target_y.ravel(), target_x.ravel()]
    )

    return interpolator(sample_points).reshape(
        target_lat.shape
    )


def _decode_observation_date(
    ds: xr.Dataset,
    filename: str,
) -> str:
    """Read the real observation date from NetCDF time metadata first."""
    if "time" in ds.variables:
        raw = ds["time"].values.squeeze()

        try:
            if isinstance(raw, np.datetime64):
                timestamp = pd.Timestamp(raw)
                return timestamp.date().isoformat()

            if hasattr(raw, "year") and hasattr(raw, "month"):
                return datetime(
                    int(raw.year),
                    int(raw.month),
                    int(raw.day),
                    tzinfo=timezone.utc,
                ).date().isoformat()

            timestamp = pd.to_datetime(raw, utc=True)
            if not pd.isna(timestamp):
                return timestamp.date().isoformat()
        except Exception:
            pass

    match = re.search(r"_(\d{8})_", filename)
    if match:
        return datetime.strptime(
            match.group(1),
            "%Y%m%d",
        ).date().isoformat()

    return ""


def _read_surface_mask(
    source: Path,
) -> tuple[np.ndarray | None, str]:
    # G10016 V4 stores surface_type_mask under cdr_supplementary.
    for group in ("cdr_supplementary", None):
        try:
            with xr.open_dataset(
                source,
                group=group,
                decode_times=False,
                mask_and_scale=False,
            ) as ds:
                if "surface_type_mask" not in ds.data_vars:
                    continue

                mask = _to_2d(
                    ds["surface_type_mask"]
                ).values.astype(float)

                return mask, (
                    "G10016 V4 surface_type_mask; "
                    "ocean=50, coast=200, land=250"
                )
        except Exception:
            continue

    return None, (
        "surface_type_mask unavailable; "
        "navigability defaults to the target grid"
    )


def _latest_file(
    directory: Path,
    patterns: tuple[str, ...],
) -> Path | None:
    """Return the newest source file, preferring the date encoded in its name."""
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(directory.glob(pattern))

    candidates = [path for path in candidates if path.is_file()]
    if not candidates:
        return None

    def key(path: Path) -> tuple[str, float, str]:
        date_match = re.search(r"(\d{4}-\d{2}-\d{2}|\d{8})", path.name)
        source_date = ""
        if date_match:
            token = date_match.group(1)
            source_date = (
                f"{token[:4]}-{token[4:6]}-{token[6:8]}"
                if len(token) == 8
                else token
            )
        return source_date, path.stat().st_mtime, path.name

    return max(candidates, key=key)


def _latest_time_value(
    da: xr.DataArray,
) -> xr.DataArray:
    for dim in da.dims:
        if dim.lower() in {"time", "valid_time", "date", "datetime"}:
            da = da.isel({dim: -1})
    da = da.squeeze(drop=True)

    # Some products can include a level/depth dimension. Choose the first
    # surface level if anything beyond lat/lon remains.
    while da.ndim > 2:
        da = da.isel({da.dims[0]: 0})

    return da


def _decode_datetime_from_value(
    raw: object,
    attrs: dict[str, object] | None = None,
) -> str:
    """Decode a NetCDF time value using its CF units/calendar when needed."""
    attrs = attrs or {}
    try:
        arr = np.asarray(raw).squeeze()
        if arr.size == 0:
            return ""
        value = arr.ravel()[-1]

        if isinstance(value, np.datetime64):
            ts = pd.Timestamp(value)
            return ts.date().isoformat()

        if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
            return f"{int(value.year):04d}-{int(value.month):02d}-{int(value.day):02d}"

        if isinstance(value, str):
            ts = pd.to_datetime(value, utc=True, errors="coerce")
            if not pd.isna(ts):
                return ts.date().isoformat()
            return ""

        units = str(attrs.get("units", ""))
        if units and np.issubdtype(arr.dtype, np.number):
            match = re.match(
                r"^\s*(seconds|minutes|hours|days|milliseconds|microseconds)\s+since\s+(.+?)\s*$",
                units,
                flags=re.IGNORECASE,
            )
            if match:
                unit = match.group(1).lower()
                origin_text = match.group(2).strip()
                origin = pd.Timestamp(origin_text)
                if origin.tzinfo is None:
                    origin = origin.tz_localize("UTC")
                else:
                    origin = origin.tz_convert("UTC")
                ts = origin + pd.to_timedelta(float(value), unit=unit)
                return ts.date().isoformat()

        ts = pd.to_datetime(value, utc=True, errors="coerce")
        if not pd.isna(ts):
            return ts.date().isoformat()
    except Exception:
        return ""
    return ""


def _decode_source_date(
    ds: xr.Dataset,
    filename: str,
) -> str:
    """Extract a source observation/analysis date with robust fallbacks."""
    # Global/file-level coverage metadata is often the most explicit source
    # for daily OSCAR products.
    for attr_name in ("time_coverage_start", "time_coverage_end", "time_start", "date"):
        value = ds.attrs.get(attr_name)
        if value:
            parsed = _decode_datetime_from_value(value)
            if parsed:
                return parsed

    for candidate in ("time", "valid_time", "date", "datetime"):
        if candidate in ds.variables:
            coord = ds[candidate]
            parsed = _decode_datetime_from_value(
                coord.values,
                dict(coord.attrs),
            )
            if parsed:
                return parsed
            # Some products put the date range in an attribute such as
            # `time_bounds: 2026-09-03 00:00:00 to ...`.
            for attr_name in ("time_bounds", "coverage_start"):
                value = coord.attrs.get(attr_name)
                if value:
                    match = re.search(r"(\d{4}-\d{2}-\d{2})", str(value))
                    if match:
                        return match.group(1)

    match = re.search(r"_(\d{8})(?:_|\.)", filename)
    if match:
        return datetime.strptime(match.group(1), "%Y%m%d").date().isoformat()

    match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    if match:
        return match.group(1)
    return ""


def _load_latlon_uv(
    path: Path,
    u_names: tuple[str, ...],
    v_names: tuple[str, ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, str]:
    """Load a latitude/longitude U/V field regardless of spatial dim order."""
    # Keep time variables in their original numeric CF representation so that
    # products with non-standard calendars (such as OSCAR's Julian calendar)
    # do not require cftime just to read the spatial fields.
    with xr.open_dataset(
        path,
        mask_and_scale=True,
        decode_times=False,
    ) as ds:
        u_da = _latest_time_value(
            _pick_variable(ds, u_names, ("u",))
        )
        v_da = _latest_time_value(
            _pick_variable(ds, v_names, ("v",))
        )

        lat_name = _coord_name(
            ds,
            ("latitude", "lat"),
        )
        lon_name = _coord_name(
            ds,
            ("longitude", "lon"),
        )

        lat_coord = ds[lat_name]
        lon_coord = ds[lon_name]

        if lat_coord.ndim != 1 or lon_coord.ndim != 1:
            raise ValueError(
                f"Expected 1D latitude/longitude coordinates in {path.name}; "
                f"got lat ndim={lat_coord.ndim}, lon ndim={lon_coord.ndim}."
            )

        lat_dim = lat_coord.dims[0]
        lon_dim = lon_coord.dims[0]

        for name, field in (("u", u_da), ("v", v_da)):
            if lat_dim not in field.dims or lon_dim not in field.dims:
                raise ValueError(
                    f"{path.name}: {name} field dimensions {field.dims} "
                    f"do not contain spatial dimensions {lat_dim!r} and "
                    f"{lon_dim!r}."
                )

        # At this point the time/extra dimensions have already been reduced.
        # Transpose explicitly by the coordinate *dimension* names. This
        # handles OSCAR files whose field is stored as (longitude, latitude).
        u_da = u_da.transpose(lat_dim, lon_dim)
        v_da = v_da.transpose(lat_dim, lon_dim)

        lat = np.asarray(
            lat_coord.values,
            dtype=float,
        ).squeeze()
        lon = np.asarray(
            lon_coord.values,
            dtype=float,
        ).squeeze()
        u = np.asarray(
            u_da.values,
            dtype=float,
        )
        v = np.asarray(
            v_da.values,
            dtype=float,
        )

        date = _decode_source_date(ds, path.name)

    if u.shape != (lat.size, lon.size) or v.shape != (lat.size, lon.size):
        raise ValueError(
            f"{path.name}: velocity field shape does not match coordinates. "
            f"u={u.shape}, v={v.shape}, expected={(lat.size, lon.size)}."
        )

    lon = _normalise_lon(lon)
    return lat, lon, u, v, date


def _find_oscar_file() -> Path | None:
    return _latest_file(
        OSCAR_DIR,
        ("*.nc",),
    )


def _find_era5_file() -> Path | None:
    return _latest_file(
        ERA5_DIR,
        ("*.nc",),
    )


def _load_optional_forcing(
    target_lat: np.ndarray,
    target_lon: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, str]]:
    """Load available real current/wind fields and regrid them to Navigator."""
    shape = target_lat.shape
    current_u = np.zeros(shape, dtype=float)
    current_v = np.zeros(shape, dtype=float)
    wind_u = np.zeros(shape, dtype=float)
    wind_v = np.zeros(shape, dtype=float)
    meta: dict[str, str] = {}

    oscar_file = _find_oscar_file()
    if oscar_file is not None:
        lat, lon, u, v, observed = _load_latlon_uv(
            oscar_file,
            ("u", "ug"),
            ("v", "vg"),
        )
        current_u = np.nan_to_num(
            _reproject_latlon(
                u,
                lon,
                lat,
                target_lat,
                target_lon,
            ),
            nan=0.0,
        )
        current_v = np.nan_to_num(
            _reproject_latlon(
                v,
                lon,
                lat,
                target_lat,
                target_lon,
            ),
            nan=0.0,
        )
        meta["current_source"] = "NASA/JPL PO.DAAC OSCAR NRT V2.0"
        meta["current_source_file"] = oscar_file.name
        meta["current_observation_date"] = observed
        meta["current_retrieved_at_utc"] = _file_retrieved_at_utc(
            oscar_file
        )

    era5_file = _find_era5_file()
    if era5_file is not None:
        lat, lon, u, v, observed = _load_latlon_uv(
            era5_file,
            (
                "u10",
                "10m_u_component_of_wind",
            ),
            (
                "v10",
                "10m_v_component_of_wind",
            ),
        )
        wind_u = np.nan_to_num(
            _reproject_latlon(
                u,
                lon,
                lat,
                target_lat,
                target_lon,
            ),
            nan=0.0,
        )
        wind_v = np.nan_to_num(
            _reproject_latlon(
                v,
                lon,
                lat,
                target_lat,
                target_lon,
            ),
            nan=0.0,
        )
        meta["wind_source"] = "Copernicus/ECMWF ERA5"
        meta["wind_source_file"] = era5_file.name
        meta["wind_observation_date"] = observed
        meta["wind_retrieved_at_utc"] = _file_retrieved_at_utc(
            era5_file
        )

    return current_u, current_v, wind_u, wind_v, meta


def main() -> None:
    files = sorted(RAW_DIR.glob("*.nc"))
    if not files:
        raise FileNotFoundError(
            f"No NSIDC NetCDF files found in {RAW_DIR}."
        )

    def file_key(path: Path) -> tuple[int, str]:
        match = re.search(
            r"_(\d{8})_",
            path.name,
        )
        return (
            int(match.group(1)) if match else 0,
            path.name,
        )

    source = max(files, key=file_key)
    target_lat, target_lon = latlon_grids()

    with xr.open_dataset(
        source,
        mask_and_scale=True,
        decode_times=True,
    ) as ds:
        da = _to_2d(
            _pick_concentration_variable(ds)
        )
        if "x" not in da.coords or "y" not in da.coords:
            raise ValueError(
                "NSIDC concentration field must provide x/y projected coordinates."
            )

        source_x = np.asarray(
            da["x"].values,
            dtype=float,
        )
        source_y = np.asarray(
            da["y"].values,
            dtype=float,
        )
        concentration = np.asarray(
            da.values,
            dtype=float,
        )

        finite = concentration[np.isfinite(concentration)]
        if finite.size and np.nanpercentile(finite, 95) > 1.5:
            concentration /= 100.0

        concentration = np.clip(
            concentration,
            0.0,
            1.0,
        )

        interpolated = _reproject_polar(
            concentration,
            source_x,
            source_y,
            target_lat,
            target_lon,
        )
        concentration_out = np.clip(
            np.nan_to_num(
                interpolated,
                nan=0.0,
            ),
            0.0,
            1.0,
        )

        observation_date = _decode_observation_date(
            ds,
            source.name,
        )

    surface_mask, surface_mask_source = _read_surface_mask(source)
    if surface_mask is not None:
        mask_grid = _reproject_polar(
            surface_mask,
            source_x,
            source_y,
            target_lat,
            target_lon,
            method="nearest",
        )
        navigable = np.isfinite(mask_grid) & (
            np.abs(mask_grid - 50.0) < 0.5
        )
    else:
        navigable = np.ones_like(
            concentration_out,
            dtype=bool,
        )

    try:
        icebergs, iceberg_meta = parse_usnic_csv()
    except FileNotFoundError:
        icebergs = []
        iceberg_meta = {}

    current_u, current_v, wind_u, wind_v, forcing_meta = _load_optional_forcing(
        target_lat,
        target_lon,
    )

    has_current = bool(np.any(np.abs(current_u) > 1e-12) or np.any(np.abs(current_v) > 1e-12))
    has_wind = bool(np.any(np.abs(wind_u) > 1e-12) or np.any(np.abs(wind_v) > 1e-12))

    forcing_parts = []
    if has_current:
        forcing_parts.append("OSCAR NRT surface currents")
    if has_wind:
        forcing_parts.append("ERA5 10-m wind")

    if forcing_parts:
        environmental_forcing = " + ".join(forcing_parts)
        trajectory_basis = "physics-based iceberg drift using available external forcing"
    else:
        environmental_forcing = "none (wind/current fields not connected)"
        trajectory_basis = "stationary fallback projection; connect OSCAR/ERA5 for forced trajectories"

    if icebergs:
        dataset_kind = "real_seaice_usnic_icebergs"
    else:
        dataset_kind = "real_seaice_only"

    access_time = datetime.now(timezone.utc).isoformat()

    meta = {
        "dataset_kind": dataset_kind,
        "source": "NOAA/NSIDC G10016 Version 4",
        "sea_ice_dataset": NSIDC_SHORT_NAME,
        "sea_ice_version": NSIDC_VERSION,
        "source_file": source.name,
        "observation_date": observation_date,
        "sea_ice_retrieved_at_utc": _file_retrieved_at_utc(source),
        "data_accessed_utc": access_time,
        "bundle_generated_at_utc": access_time,
        "projection": "EPSG:3412",
        "resolution_km": 25,
        "surface_mask_source": surface_mask_source,
        "iceberg_source": iceberg_meta.get(
            "source",
            "none",
        ),
        "iceberg_source_file": iceberg_meta.get(
            "source_file",
            "",
        ),
        "iceberg_records_used": int(
            iceberg_meta.get(
                "records_used",
                len(icebergs),
            )
        ),
        "iceberg_observation_date": iceberg_meta.get(
            "latest_source_update",
            "",
        ),
        "iceberg_retrieved_at_utc": (
            _file_retrieved_at_utc(
                RAW_DIR / str(iceberg_meta.get("source_file", ""))
            )
            if iceberg_meta.get("source_file")
            and (RAW_DIR / str(iceberg_meta.get("source_file"))).exists()
            else ""
        ),
        "environmental_forcing": environmental_forcing,
        "trajectory_basis": trajectory_basis,
        "current_source": forcing_meta.get(
            "current_source",
            "",
        ),
        "current_source_file": forcing_meta.get(
            "current_source_file",
            "",
        ),
        "current_observation_date": forcing_meta.get(
            "current_observation_date",
            "",
        ),
        "current_retrieved_at_utc": forcing_meta.get(
            "current_retrieved_at_utc",
            "",
        ),
        "wind_source": forcing_meta.get(
            "wind_source",
            "",
        ),
        "wind_source_file": forcing_meta.get(
            "wind_source_file",
            "",
        ),
        "wind_observation_date": forcing_meta.get(
            "wind_observation_date",
            "",
        ),
        "wind_retrieved_at_utc": forcing_meta.get(
            "wind_retrieved_at_utc",
            "",
        ),
        "historical_validation_source": "BYU/NIC consolidated database v8.0",
        "day_of_year": (
            datetime.strptime(
                observation_date,
                "%Y-%m-%d",
            ).timetuple().tm_yday
            if observation_date
            else 1
        ),
        "grid": {
            "rows": int(target_lat.shape[0]),
            "cols": int(target_lat.shape[1]),
        },
        "note": (
            "G10016 V4 is a near-real-time sea-ice concentration input. "
            "USNIC provides current iceberg observations. OSCAR and ERA5 are "
            "optional environmental forcing inputs for the drift model. "
            "Partial sea ice is risk-weighted; 100% concentration cells are "
            "hard exclusions. This is decision-support software, not certified navigation."
        ),
    }

    bundle = {
        "meta": meta,
        "lat_grid": target_lat.tolist(),
        "lon_grid": target_lon.tolist(),
        "concentration": concentration_out.tolist(),
        "current_u": current_u.tolist(),
        "current_v": current_v.tolist(),
        "wind_u": wind_u.tolist(),
        "wind_v": wind_v.tolist(),
        "navigable_mask": navigable.tolist(),
        "icebergs": icebergs,
    }

    OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUT.write_text(
        json.dumps(
            bundle,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"Navigator bundle written: {OUT}"
    )
    print(
        f"Dataset: {dataset_kind} | sea ice: {observation_date or 'unknown'} | "
        f"icebergs: {len(icebergs)} | forcing: {environmental_forcing}"
    )


if __name__ == "__main__":
    main()
