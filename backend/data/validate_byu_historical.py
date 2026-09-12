"""Validate an extracted BYU/NIC historical iceberg database."""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

HISTORICAL_ROOT = (
    Path(__file__).resolve().parent
    / "real"
    / "historical"
    / "byu_v8.0"
)


def _norm(value: Any) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "",
        str(value or "").lower(),
    )


def _find_field(
    fields: list[str],
    names: tuple[str, ...],
) -> str | None:
    normalized = {
        _norm(field): field
        for field in fields
    }
    for name in names:
        if _norm(name) in normalized:
            return normalized[_norm(name)]
    return None


def validate(
    root: str | Path = HISTORICAL_ROOT,
) -> dict[str, Any]:
    root = Path(root)
    csv_files = sorted(root.rglob("*.csv"))

    if not csv_files:
        raise FileNotFoundError(
            f"No BYU/NIC CSV files found under {root}"
        )

    rows_checked = 0
    coordinate_rows = 0
    files_with_coordinate_fields = 0

    for path in csv_files:
        with path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames or []
            lat_field = _find_field(
                fields,
                ("latitude", "lat", "mean latitude"),
            )
            lon_field = _find_field(
                fields,
                ("longitude", "lon", "mean longitude"),
            )

            if lat_field and lon_field:
                files_with_coordinate_fields += 1

            for row in reader:
                rows_checked += 1
                if lat_field and lon_field:
                    try:
                        float(str(row.get(lat_field, "")).strip())
                        float(str(row.get(lon_field, "")).strip())
                    except (TypeError, ValueError):
                        continue
                    coordinate_rows += 1

    return {
        "root": str(root),
        "csv_files": len(csv_files),
        "rows_checked": rows_checked,
        "files_with_coordinate_fields": files_with_coordinate_fields,
        "rows_with_numeric_coordinates": coordinate_rows,
        "status": "ok",
    }


if __name__ == "__main__":
    print(validate())
