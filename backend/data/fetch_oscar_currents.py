"""Refresh NASA/JPL PO.DAAC OSCAR NRT surface currents.

The OSCAR NRT collection is daily with an approximate two-day latency, but
CMR granule indexing/publication can occasionally lag or have gaps. This
refresh script therefore searches a generous look-back window and safely
keeps the newest cached OSCAR file when no new granule is returned.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

COLLECTION = "OSCAR_L4_OC_NRT_V2.0"
ENV_ROOT = (
    Path(__file__).resolve().parent
    / "real"
    / "raw"
    / "environmental"
    / "oscar"
)
DEFAULT_LOOKBACK_DAYS = 30
SEARCH_COUNT = 10


def _cached_files() -> list[Path]:
    """Return cached OSCAR NetCDF files, newest first."""
    ENV_ROOT.mkdir(parents=True, exist_ok=True)
    files = [p for p in ENV_ROOT.glob("*.nc") if p.is_file()]

    def sort_key(path: Path):
        match = re.search(r"(\d{8})", path.name)
        if match:
            try:
                stamp = datetime.strptime(match.group(1), "%Y%m%d")
                return (stamp, path.stat().st_mtime)
            except ValueError:
                pass
        return (datetime.min, path.stat().st_mtime)

    return sorted(files, key=sort_key, reverse=True)


def _search(earthaccess, start: datetime, end: datetime):
    """Search OSCAR using the supported short-name filter."""
    return earthaccess.search_data(
        short_name=COLLECTION,
        cloud_hosted=True,
        temporal=(
            start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
        count=SEARCH_COUNT,
    )


def download_latest() -> list[Path]:
    try:
        import earthaccess
    except ImportError as exc:
        raise RuntimeError(
            "earthaccess is required. Run: pip install -r requirements.txt"
        ) from exc

    ENV_ROOT.mkdir(parents=True, exist_ok=True)

    try:
        earthaccess.login(strategy="interactive", persist=True)
    except Exception as exc:
        cached = _cached_files()
        if cached:
            print(
                "WARNING: OSCAR Earthdata authentication failed. "
                f"Keeping cached OSCAR file: {cached[0]}"
            )
            return []
        raise RuntimeError(
            "OSCAR Earthdata authentication failed and no cached OSCAR file exists."
        ) from exc

    end = datetime.now(timezone.utc)
    lookback_days = DEFAULT_LOOKBACK_DAYS

    # The first search uses a 30-day window. This is intentionally wider than
    # the product's nominal ~2-day latency so a short CMR publication gap or
    # delayed indexing does not make a valid existing product look absent.
    try:
        results = _search(
            earthaccess,
            end - timedelta(days=lookback_days),
            end,
        )
    except Exception as exc:
        cached = _cached_files()
        if cached:
            print(
                "WARNING: OSCAR CMR search failed. "
                f"Keeping cached OSCAR file: {cached[0]}"
            )
            return []
        raise RuntimeError(
            f"Could not search {COLLECTION} and no cached OSCAR file exists."
        ) from exc

    if not results:
        cached = _cached_files()
        if cached:
            print(
                f"WARNING: No OSCAR granules were returned in the last "
                f"{lookback_days} days."
            )
            print(f"Keeping cached OSCAR file: {cached[0]}")
            print(
                "The cached file will remain visible in the bundle with its "
                "actual observation date; this is not silently labelled as current."
            )
            return []

        raise RuntimeError(
            f"No OSCAR granules found for {COLLECTION} in the last "
            f"{lookback_days} days, and no cached OSCAR file exists."
        )

    downloaded = earthaccess.download(
        results,
        local_path=str(ENV_ROOT),
    )

    paths = [Path(item) for item in downloaded if Path(item).is_file()]
    if not paths:
        cached = _cached_files()
        if cached:
            print(
                "WARNING: OSCAR search returned records but no files were downloaded. "
                f"Keeping cached OSCAR file: {cached[0]}"
            )
            return []
        raise RuntimeError("OSCAR download returned no files and no cached file exists.")

    for path in paths:
        print(f"OSCAR downloaded: {path}")

    return paths


if __name__ == "__main__":
    try:
        paths = download_latest()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

    if not paths:
        # A zero exit status is intentional when a usable cached OSCAR file is
        # being retained. daily_refresh.ps1 can then continue to conversion
        # and validation instead of treating a temporary source gap as fatal.
        print("OSCAR refresh completed using the existing cached data.")
    else:
        for path in paths:
            print(path)
