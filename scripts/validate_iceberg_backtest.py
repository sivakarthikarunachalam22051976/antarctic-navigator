from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any


EARTH_RADIUS_KM = 6371.0088


def parse_date(value: Any) -> datetime | None:
    text = str(value or "").strip()

    if not text:
        return None

    # BYU/NIC format: YYYYDDD
    if re.fullmatch(r"\d{7}", text):
        try:
            year = int(text[:4])
            doy = int(text[4:])
            if 1 <= doy <= 366:
                return datetime(year, 1, 1) + timedelta(days=doy - 1)
        except ValueError:
            return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass

    return None


def clean_field(name: Any) -> str:
    return str(name or "").strip().lower()


def pick(fields: list[str], aliases: tuple[str, ...]) -> str | None:
    normalized = {clean_field(field): field for field in fields}

    for alias in aliases:
        key = clean_field(alias)
        if key in normalized:
            return normalized[key]

    return None


def parse_float(value: Any) -> float | None:
    text = str(value or "").strip()

    if not text:
        return None

    try:
        value = float(text)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(value):
        return None

    return value


def valid_lat_lon(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False

    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def extract_position(row: dict[str, Any]) -> tuple[float, float] | None:
    """
    BYU/NIC v8.0 contains several possible coordinate sources.

    Preferred order:
      1. NIC
      2. ASCAT
      3. OSCAT
      4. QSCAT
      5. ERS

    Each latitude/longitude pair is selected together so that
    latitude and longitude never accidentally come from different sensors.
    """

    coordinate_pairs = (
        ("nic_1", "nic_2"),
        ("ascat_1", "ascat_2"),
        ("oscat_1", "oscat_2"),
        ("qscat_1", "qscat_2"),
        ("ers_1", "ers_2"),
    )

    normalized_row = {
        clean_field(key): value
        for key, value in row.items()
    }

    for lat_key, lon_key in coordinate_pairs:
        lat = parse_float(normalized_row.get(lat_key))
        lon = parse_float(normalized_row.get(lon_key))

        if valid_lat_lon(lat, lon):
            return lat, lon

    return None


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(dlon / 2.0) ** 2
    )

    a = min(1.0, max(0.0, a))

    return 2.0 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def load_tracks(
    root: Path,
    min_points: int = 4,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    csv_files = sorted(
        path
        for path in root.rglob("*.csv")
        if path.is_file()
    )

    stats = {
        "csv_files_scanned": len(csv_files),
        "rows_seen": 0,
        "usable_rows": 0,
        "files_with_usable_rows": 0,
        "files_skipped_no_date": 0,
        "files_skipped_no_coordinates": 0,
    }

    for path in csv_files:
        # Ignore temporary/editor backup files such as #d15b.csv#
        if path.name.endswith("#"):
            continue

        try:
            with path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as handle:
                reader = csv.DictReader(handle)

                fields = reader.fieldnames or []

                date_field = pick(
                    fields,
                    (
                        "date",
                        "day",
                        "yyyydoy",
                    ),
                )

                if not date_field:
                    stats["files_skipped_no_date"] += 1
                    continue

                file_usable_rows = 0

                for row in reader:
                    stats["rows_seen"] += 1

                    dt = parse_date(row.get(date_field))

                    if dt is None:
                        continue

                    position = extract_position(row)

                    if position is None:
                        continue

                    lat, lon = position

                    key = path.stem

                    groups[key].append(
                        {
                            "id": key,
                            "date": dt,
                            "lat": lat,
                            "lon": lon,
                            "source_file": path.name,
                        }
                    )

                    stats["usable_rows"] += 1
                    file_usable_rows += 1

                if file_usable_rows:
                    stats["files_with_usable_rows"] += 1
                else:
                    stats["files_skipped_no_coordinates"] += 1

        except (OSError, UnicodeError, csv.Error):
            continue

    tracks: list[dict[str, Any]] = []

    for key, rows in groups.items():
        rows.sort(key=lambda x: x["date"])

        # Remove duplicate calendar dates inside a track.
        by_date: dict[Any, dict[str, Any]] = {}

        for row in rows:
            by_date[row["date"].date()] = row

        cleaned_rows = [
            by_date[date]
            for date in sorted(by_date)
        ]

        if len(cleaned_rows) >= min_points:
            tracks.append(
                {
                    "id": key,
                    "rows": cleaned_rows,
                }
            )

    stats["tracks"] = len(tracks)

    return tracks, stats


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0

    values = sorted(values)

    if len(values) == 1:
        return values[0]

    position = (len(values) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return values[lower]

    fraction = position - lower

    return (
        values[lower]
        + (values[upper] - values[lower]) * fraction
    )


def run_benchmark(
    tracks: list[dict[str, Any]],
    horizons: list[int],
) -> dict[str, Any]:

    errors: dict[int, list[float]] = {
        horizon: []
        for horizon in horizons
    }

    samples: dict[int, int] = {
        horizon: 0
        for horizon in horizons
    }

    for track in tracks:
        rows = track["rows"]

        by_date = {
            row["date"].date(): row
            for row in rows
        }

        for start_date, start in sorted(by_date.items()):

            # Strict initialization requirement:
            # the previous observation must exist exactly one
            # calendar day before the starting observation.
            previous = by_date.get(
                start_date - timedelta(days=1)
            )

            if previous is None:
                continue

            # Constant-velocity displacement from the immediately
            # preceding daily observation.
            v_lat = start["lat"] - previous["lat"]
            v_lon = start["lon"] - previous["lon"]

            for horizon in horizons:

                future = by_date.get(
                    start_date + timedelta(days=horizon)
                )

                # Strict exact-date matching.
                if future is None:
                    continue

                predicted_lat = (
                    start["lat"] + v_lat * horizon
                )

                predicted_lon = (
                    start["lon"] + v_lon * horizon
                )

                error_km = haversine_km(
                    predicted_lat,
                    predicted_lon,
                    future["lat"],
                    future["lon"],
                )

                errors[horizon].append(error_km)
                samples[horizon] += 1

    metrics: dict[str, Any] = {}

    for horizon in horizons:
        values = errors[horizon]

        if not values:
            metrics[str(horizon)] = {
                "samples": 0,
                "median_error_km": None,
                "mae_km": None,
                "rmse_km": None,
                "p90_error_km": None,
                "p95_error_km": None,
                "max_error_km": None,
                "errors_over_100km": 0,
                "model": "constant-velocity historical benchmark",
            }
            continue

        mae = mean(values)

        rmse = math.sqrt(
            mean(
                value * value
                for value in values
            )
        )

        metrics[str(horizon)] = {
            "samples": samples[horizon],
            "median_error_km": median(values),
            "mae_km": mae,
            "rmse_km": rmse,
            "p90_error_km": percentile(values, 0.90),
            "p95_error_km": percentile(values, 0.95),
            "max_error_km": max(values),
            "errors_over_100km": sum(
                value > 100.0
                for value in values
            ),
            "model": "constant-velocity historical benchmark",
        }

    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Strict historical iceberg benchmark using "
            "BYU/NIC consolidated database v8.0."
        )
    )

    parser.add_argument(
        "--tracks",
        required=True,
        help="Extracted BYU/NIC v8.0 directory",
    )

    parser.add_argument(
        "--horizons",
        nargs="+",
        type=int,
        default=[1, 3],
        help="Forecast horizons in calendar days",
    )

    args = parser.parse_args()

    root = Path(args.tracks)

    if not root.exists():
        raise SystemExit(
            f"Historical iceberg directory not found: {root}"
        )

    tracks, parse_stats = load_tracks(root)

    if not tracks:
        raise SystemExit(
            "No usable historical iceberg tracks found."
        )

    metrics = run_benchmark(
        tracks,
        args.horizons,
    )

    result = {
        "status": "benchmark_only",
        "tracks": len(tracks),
        "source": (
            "BYU/NIC consolidated Antarctic "
            "iceberg database v8.0"
        ),
        "matching_method": (
            "Strict exact calendar-date matching. "
            "Initialization requires an observation "
            "exactly one day before the start date."
        ),
        "coordinate_source_priority": [
            "NIC",
            "ASCAT",
            "OSCAT",
            "QSCAT",
            "ERS",
        ],
        "parse_stats": parse_stats,
        "warning": (
            "This run scores a transparent constant-velocity "
            "benchmark. It does NOT claim RK4 historical "
            "validation because matching historical "
            "current/wind forcing was not supplied."
        ),
        "metrics": metrics,
    }

    print(
        json.dumps(
            result,
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
