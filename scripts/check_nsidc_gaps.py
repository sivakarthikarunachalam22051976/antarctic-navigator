"""
Check a historical NSIDC G02202 directory for calendar gaps.

Important:
- Searches recursively through all subdirectories.
- Extracts dates directly from NSIDC filenames.
- Counts UNIQUE observation dates, not raw files.
- Reports duplicate files separately.
- Never synthesizes, interpolates, or invents missing observations.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path


# Example:
# sic_pss25_20250131_am2_v06r00.nc
PATTERN = re.compile(
    r"^sic_pss25_(\d{8})_[^/\\]+\.nc$",
    re.IGNORECASE,
)


def parse_date_from_filename(filename: str) -> date | None:
    """Extract YYYYMMDD from an NSIDC G02202 filename."""

    match = PATTERN.match(filename)

    if not match:
        return None

    raw = match.group(1)

    try:
        return date(
            int(raw[0:4]),
            int(raw[4:6]),
            int(raw[6:8]),
        )
    except ValueError:
        return None


def daterange(start: date, end: date):
    """Yield every calendar date from start through end."""

    current = start

    while current <= end:
        yield current
        current += timedelta(days=1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Check historical NSIDC G02202 daily files for "
            "calendar-date gaps without inventing data."
        )
    )

    parser.add_argument(
        "--data-dir",
        required=True,
        help="Directory containing NSIDC .nc files.",
    )

    parser.add_argument(
        "--output",
        default="validation/nsidc_gap_report.json",
        help="Output JSON report path.",
    )

    args = parser.parse_args()

    root = Path(args.data_dir)

    if not root.exists():
        raise SystemExit(
            f"ERROR: Data directory does not exist: {root}"
        )

    if not root.is_dir():
        raise SystemExit(
            f"ERROR: Data path is not a directory: {root}"
        )

    # ------------------------------------------------------------------
    # IMPORTANT FIX:
    #
    # Use rglob() instead of glob().
    #
    # The old script used:
    #     root.glob("*.nc")
    #
    # That only checks the immediate directory.
    #
    # Your PowerShell diagnostic used -Recurse and therefore found files
    # inside subdirectories. This mismatch caused false missing dates.
    # ------------------------------------------------------------------

    files = sorted(
        f for f in root.rglob("*.nc")
        if f.is_file()
    )

    files_by_date: dict[date, list[Path]] = defaultdict(list)
    ignored_files: list[str] = []

    for file_path in files:
        observation_date = parse_date_from_filename(file_path.name)

        if observation_date is None:
            ignored_files.append(
                str(file_path.relative_to(root))
            )
            continue

        files_by_date[observation_date].append(file_path)

    if not files_by_date:
        raise SystemExit(
            "ERROR: No NSIDC G02202 daily files were found."
        )

    # ------------------------------------------------------------------
    # Work with UNIQUE observation dates.
    #
    # Multiple files for the same date are not multiple days.
    # ------------------------------------------------------------------

    unique_dates = sorted(files_by_date.keys())

    start_date = unique_dates[0]
    end_date = unique_dates[-1]

    expected_dates = set(
        daterange(start_date, end_date)
    )

    actual_dates = set(unique_dates)

    missing_dates = sorted(
        expected_dates - actual_dates
    )

    duplicate_dates = {
        observation_date: paths
        for observation_date, paths in files_by_date.items()
        if len(paths) > 1
    }

    duplicate_file_count = sum(
        len(paths) - 1
        for paths in duplicate_dates.values()
    )

    # ------------------------------------------------------------------
    # Identify continuous missing intervals.
    # ------------------------------------------------------------------

    missing_intervals = []

    if missing_dates:
        interval_start = missing_dates[0]
        previous = missing_dates[0]

        for current in missing_dates[1:]:
            if current == previous + timedelta(days=1):
                previous = current
                continue

            missing_intervals.append(
                {
                    "start_date": interval_start.isoformat(),
                    "end_date": previous.isoformat(),
                    "missing_days": (
                        previous - interval_start
                    ).days + 1,
                }
            )

            interval_start = current
            previous = current

        missing_intervals.append(
            {
                "start_date": interval_start.isoformat(),
                "end_date": previous.isoformat(),
                "missing_days": (
                    previous - interval_start
                ).days + 1,
            }
        )

    # ------------------------------------------------------------------
    # Duplicate-date report.
    # ------------------------------------------------------------------

    duplicate_report = []

    for observation_date in sorted(duplicate_dates):
        duplicate_report.append(
            {
                "date": observation_date.isoformat(),
                "file_count": len(
                    duplicate_dates[observation_date]
                ),
                "files": [
                    str(path.relative_to(root))
                    for path in sorted(
                        duplicate_dates[observation_date]
                    )
                ],
            }
        )

    # ------------------------------------------------------------------
    # Final report.
    # ------------------------------------------------------------------

    result = {
        "status": (
            "ok"
            if not missing_dates
            else "gap_detected"
        ),

        "dataset": "NSIDC G02202 V6 Antarctic daily sea-ice concentration",

        # Raw .nc files discovered recursively.
        "files_found_raw": len(files),

        # Files with recognizable NSIDC observation dates.
        "files_with_valid_dates": sum(
            len(paths)
            for paths in files_by_date.values()
        ),

        # IMPORTANT:
        # This is the number that matters for calendar coverage.
        "unique_observation_dates": len(unique_dates),

        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),

        "missing_dates": [
            observation_date.isoformat()
            for observation_date in missing_dates
        ],

        "missing_day_count": len(missing_dates),

        "missing_intervals": missing_intervals,

        "duplicate_date_count": len(
            duplicate_dates
        ),

        "duplicate_file_count": duplicate_file_count,

        "duplicate_dates": duplicate_report,

        "ignored_nonmatching_nc_files": len(
            ignored_files
        ),

        "note": (
            "Missing dates are reported only. "
            "No observations are synthesized, interpolated, "
            "duplicated, or substituted."
        ),

        "methodology_note": (
            "Calendar coverage is evaluated using unique dates "
            "parsed from NSIDC filenames across the entire "
            "directory tree. Multiple files representing the "
            "same observation date are treated as duplicate "
            "files, not additional observation days."
        ),
    }

    # ------------------------------------------------------------------
    # Save report.
    # ------------------------------------------------------------------

    output_path = Path(args.output)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            result,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ------------------------------------------------------------------
    # Console output.
    # ------------------------------------------------------------------

    print(
        json.dumps(
            result,
            indent=2,
        )
    )

    print()
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()