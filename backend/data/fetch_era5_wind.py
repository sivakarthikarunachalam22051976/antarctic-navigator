"""Download a recent ERA5 10-m wind field for the Antarctic operating region.

ERA5 is a reanalysis product, not an instantaneous live forecast. The default
selection is seven days behind UTC today to allow for normal publication
latency; override with ERA5_DATE=YYYY-MM-DD or ERA5_LAG_DAYS=N.

Authentication can be supplied in either of the official cdsapi ways:
1. %USERPROFILE%\\.cdsapirc with:
       url: https://cds.climate.copernicus.eu/api
       key: <PERSONAL-ACCESS-TOKEN>
2. Environment variables CDSAPI_URL and CDSAPI_KEY.

Never commit the personal access token to the repository.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

OUTPUT_DIR = (
    Path(__file__).resolve().parent
    / "real"
    / "raw"
    / "environmental"
    / "era5"
)

DEFAULT_CDS_URL = "https://cds.climate.copernicus.eu/api"
DATASET = "reanalysis-era5-single-levels"


def _target_date() -> date:
    text = os.getenv("ERA5_DATE", "").strip()
    if text:
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(
                "ERA5_DATE must use YYYY-MM-DD, for example 2026-09-01."
            ) from exc

    try:
        lag = int(os.getenv("ERA5_LAG_DAYS", "7"))
    except ValueError as exc:
        raise ValueError("ERA5_LAG_DAYS must be an integer.") from exc

    if lag < 0:
        raise ValueError("ERA5_LAG_DAYS cannot be negative.")

    return datetime.now(timezone.utc).date() - timedelta(days=lag)


def _make_client(cdsapi):
    """Create a cdsapi client using env vars when present, otherwise .cdsapirc."""
    url = os.getenv("CDSAPI_URL", "").strip() or DEFAULT_CDS_URL
    key = os.getenv("CDSAPI_KEY", "").strip()

    if key:
        return cdsapi.Client(
            url=url,
            key=key,
        )

    config_path = Path.home() / ".cdsapirc"
    if not config_path.exists():
        raise RuntimeError(
            "ERA5 requires Copernicus CDS API credentials.\n\n"
            "Option A (recommended on Windows): create this file once:\n"
            f"  {config_path}\n\n"
            "with the two lines copied from your CDS profile:\n"
            "  url: https://cds.climate.copernicus.eu/api\n"
            "  key: <YOUR-PERSONAL-ACCESS-TOKEN>\n\n"
            "Option B: set CDSAPI_URL and CDSAPI_KEY in the environment.\n"
            "Do not commit your token to GitHub.\n\n"
            "You must also accept the ERA5 dataset Terms of Use in the CDS "
            "download page before the API request can succeed."
        )

    return cdsapi.Client()


def download_era5() -> Path:
    try:
        import cdsapi
    except ImportError as exc:
        raise RuntimeError(
            "cdsapi is required. Run: pip install -r requirements.txt"
        ) from exc

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = _target_date()
    output = OUTPUT_DIR / f"era5_wind_{target.isoformat()}.nc"

    client = _make_client(cdsapi)

    request = {
        "product_type": ["reanalysis"],
        "variable": [
            "10m_u_component_of_wind",
            "10m_v_component_of_wind",
        ],
        "year": [target.strftime("%Y")],
        "month": [target.strftime("%m")],
        "day": [target.strftime("%d")],
        "time": ["00:00", "06:00", "12:00", "18:00"],
        "area": [-65.0, 0.0, -75.0, 90.0],
        "grid": [0.25, 0.25],
        "data_format": "netcdf",
    }

    print(f"ERA5 target date: {target.isoformat()}")
    print(f"Saving to: {output}")
    client.retrieve(
        DATASET,
        request,
        str(output),
    )

    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError("ERA5 wind download produced no usable file.")

    print(f"ERA5 wind downloaded: {output}")
    return output


if __name__ == "__main__":
    download_era5()
