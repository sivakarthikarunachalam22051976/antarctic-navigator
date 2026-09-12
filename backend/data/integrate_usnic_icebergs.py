"""Normalize a current USNIC Antarctic iceberg CSV into Navigator records."""
from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from config import GRID_LAT_MAX, GRID_LAT_MIN, GRID_LON_MAX, GRID_LON_MIN

REAL_DIR = Path(__file__).resolve().parent / "real"
RAW_DIR = REAL_DIR / "raw"
DEFAULT_CSV = RAW_DIR / "usnic_antarctic_icebergs.csv"


def _norm_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _pick(row: dict[str, Any], candidates: tuple[str, ...]) -> Any:
    normalized = {_norm_key(k): v for k, v in row.items()}
    for candidate in candidates:
        value = normalized.get(_norm_key(candidate))
        if value not in (None, ""):
            return value
    return None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def _parse_coordinate(value: Any, hemisphere: str | None = None) -> float | None:
    if value is None:
        return None

    text = str(value).strip().upper()
    if not text:
        return None

    # Decimal degrees, optionally followed by a hemisphere.
    try:
        number = float(text.replace("°", "").strip())
        hemi = (hemisphere or "").strip().upper()
        if hemi in {"S", "W"}:
            return -abs(number)
        if hemi in {"N", "E"}:
            return abs(number)
        if text.endswith(("S", "W")):
            return -abs(number)
        if text.endswith(("N", "E")):
            return abs(number)
        return number
    except ValueError:
        pass

    hemi = next((h for h in "NSEW" if h in text), None)
    hemi = hemi or (hemisphere or "").strip().upper() or None

    nums = [
        float(x)
        for x in re.findall(r"[-+]?\d+(?:\.\d+)?", text)
    ]
    if not nums:
        return None

    degrees = abs(nums[0])
    minutes = abs(nums[1]) if len(nums) > 1 else 0.0
    seconds = abs(nums[2]) if len(nums) > 2 else 0.0
    result = degrees + minutes / 60.0 + seconds / 3600.0

    if hemi in {"S", "W"} or text.startswith("-"):
        result = -result

    return result


def _parse_location_pair(value: Any) -> tuple[float | None, float | None]:
    if value is None:
        return None, None

    text = str(value).strip().upper()
    parts = re.split(r"\s*/\s*", text)
    if len(parts) != 2:
        return None, None

    lat = _parse_coordinate(parts[0])
    lon = _parse_coordinate(parts[1])
    return lat, lon


def _parse_size_pair(value: Any) -> tuple[float | None, float | None]:
    if value is None:
        return None, None
    numbers = re.findall(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
    if len(numbers) < 2:
        return None, None
    return float(numbers[0]), float(numbers[1])


def _parse_size_km(value: Any, unit_hint: str = "") -> float | None:
    number = _number(value)
    if number is None:
        return None
    text = f"{value} {unit_hint}".lower()
    if "nm" in text or "nautical" in text:
        return number * 1.852
    return number


def _normalise_update_date(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""

    for fmt in (
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d",
        "%m-%d-%Y",
        "%m-%d-%y",
        "%B %d, %Y",
        "%b %d, %Y",
    ):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass

    match = re.search(r"(\d{4})[-/]?(\d{2})[-/]?(\d{2})", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

    return text


def _find_csv(explicit: str | None = None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise FileNotFoundError(f"USNIC CSV not found: {path}")
        return path

    candidates = [
        DEFAULT_CSV,
        *sorted(RAW_DIR.glob("*iceberg*.csv")),
        *sorted(RAW_DIR.glob("*.csv")),
    ]

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            return resolved

    raise FileNotFoundError(
        "No USNIC iceberg CSV found. Put the downloaded file at "
        f"{DEFAULT_CSV} or download it with fetch_usnic_icebergs.py."
    )


def parse_usnic_csv(
    csv_path: str | Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = _find_csv(str(csv_path) if csv_path else None)
    icebergs: list[dict[str, Any]] = []
    skipped = 0

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        sample = handle.read(8192)
        handle.seek(0)

        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            dialect = csv.excel

        reader = csv.DictReader(handle, dialect=dialect)

        for row in reader:
            name = _pick(
                row,
                (
                    "iceberg",
                    "name",
                    "id",
                    "iceberg name",
                ),
            )

            lat_raw = _pick(
                row,
                (
                    "latitude",
                    "lat",
                    "latitude deg",
                    "lat deg",
                ),
            )
            lon_raw = _pick(
                row,
                (
                    "longitude",
                    "lon",
                    "long",
                    "longitude deg",
                    "lon deg",
                ),
            )

            lat_hemi = _pick(
                row,
                (
                    "lat hemisphere",
                    "latitude hemisphere",
                    "ns",
                ),
            )
            lon_hemi = _pick(
                row,
                (
                    "lon hemisphere",
                    "longitude hemisphere",
                    "ew",
                ),
            )

            lat = _parse_coordinate(
                lat_raw,
                str(lat_hemi) if lat_hemi else None,
            )
            lon = _parse_coordinate(
                lon_raw,
                str(lon_hemi) if lon_hemi else None,
            )

            # The official USNIC product also presents location as a single
            # latitude / longitude field. Support that representation too.
            if lat is None or lon is None:
                location = _pick(
                    row,
                    (
                        "location",
                        "position",
                        "coordinates",
                    ),
                )
                loc_lat, loc_lon = _parse_location_pair(location)
                lat = lat if lat is not None else loc_lat
                lon = lon if lon is not None else loc_lon

            if not name or lat is None or lon is None:
                skipped += 1
                continue

            if not (
                GRID_LAT_MIN <= lat <= GRID_LAT_MAX
                and GRID_LON_MIN <= lon <= GRID_LON_MAX
            ):
                skipped += 1
                continue

            size_raw = _pick(
                row,
                (
                    "size",
                    "dimensions",
                    "size (nm)",
                ),
            )
            size_length_nm, size_width_nm = _parse_size_pair(size_raw)

            length = _pick(
                row,
                (
                    "length",
                    "length nm",
                    "length (nm)",
                    "longest axis",
                ),
            )
            width = _pick(
                row,
                (
                    "width",
                    "width nm",
                    "width (nm)",
                ),
            )

            if length is None and size_length_nm is not None:
                length = size_length_nm
            if width is None and size_width_nm is not None:
                width = size_width_nm

            length_km = _parse_size_km(length, "nm") or 0.0
            width_km = _parse_size_km(width, "nm") or 0.0

            size_km = max(
                length_km,
                width_km,
                1.0,
            )

            region = _pick(
                row,
                ("region",),
            )
            updated = _pick(
                row,
                (
                    "last update",
                    "last_update",
                    "date",
                    "updated",
                    "update date",
                ),
            )

            icebergs.append(
                {
                    "id": str(name).strip(),
                    "lat": float(lat),
                    "lon": float(lon),
                    "length_km": round(size_km, 3),
                    "width_km": round(width_km, 3),
                    "source": "USNIC",
                    "region": str(region).strip() if region else "",
                    "source_updated": _normalise_update_date(updated),
                }
            )

    # Prefer the latest row for a repeated iceberg ID.
    deduped: dict[str, dict[str, Any]] = {}
    for item in icebergs:
        deduped[item["id"]] = item

    update_dates = sorted(
        {
            item["source_updated"]
            for item in deduped.values()
            if item.get("source_updated")
        }
    )

    metadata = {
        "source": "U.S. National Ice Center (USNIC)",
        "source_file": path.name,
        "records_read": len(icebergs) + skipped,
        "records_used": len(deduped),
        "records_skipped": skipped,
        "latest_source_update": update_dates[-1] if update_dates else "",
        "retrieved_at_utc": datetime.fromtimestamp(
            path.stat().st_mtime,
            tz=timezone.utc,
        ).isoformat(),
        "operating_window": {
            "lat_min": GRID_LAT_MIN,
            "lat_max": GRID_LAT_MAX,
            "lon_min": GRID_LON_MIN,
            "lon_max": GRID_LON_MAX,
        },
    }

    return list(deduped.values()), metadata


if __name__ == "__main__":
    items, meta = parse_usnic_csv()
    print(f"USNIC records used: {len(items)}")
    print(meta)
