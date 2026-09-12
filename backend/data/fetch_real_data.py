"""Download the latest Antarctic sea-ice file from NSIDC G10016 Version 4.

This uses NSIDC's official NOAA@NSIDC HTTPS file system directly instead of
NASA CMR granule search. The current G10016 Version 4 Antarctic files live
under:

https://noaadata.apps.nsidc.org/NOAA/G10016_V4/south/daily/

The script automatically:
1. Finds the newest available Antarctic daily NetCDF file.
2. Downloads only that newest file into backend/data/real/raw/.
3. Keeps G10016 Version 4 as the default, so no PowerShell environment
   variables are required for normal use.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


DEFAULT_SHORT_NAME = "G10016"
DEFAULT_VERSION = "4"

RAW_DIR = Path(__file__).resolve().parent / "real" / "raw"
BASE_URL_TEMPLATE = (
    "https://noaadata.apps.nsidc.org/NOAA/"
    "{short_name}_V{version}/south/daily/"
)

# G10016 Antarctic daily files have this naming pattern.
FILE_RE = re.compile(
    r"^sic_pss25_(\d{8})_.*_v04r00\.nc$",
    re.IGNORECASE,
)

HEADERS = {
    "User-Agent": "Antarctic-Navigator/1.0 (SIH26059 prototype)"
}


def _get_year_index(year: int, base_url: str) -> str:
    url = urljoin(base_url, f"{year}/")

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()
    return response.text


def _find_latest_file(base_url: str) -> tuple[int, str]:
    """Return (year, filename) for the newest available Antarctic G10016 file."""
    current_year = datetime.now(timezone.utc).year

    # Check the current year first, then previous two years in case a
    # publication gap or server indexing delay exists.
    for year in range(
        current_year,
        current_year - 3,
        -1,
    ):
        try:
            html = _get_year_index(
                year,
                base_url,
            )
        except requests.RequestException:
            continue

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        candidates: list[tuple[datetime, str]] = []

        for link in soup.find_all(
            "a",
            href=True,
        ):
            href = str(
                link["href"]
            ).split(
                "?",
                1,
            )[0]

            filename = href.rsplit(
                "/",
                1,
            )[-1]

            match = FILE_RE.match(filename)

            if not match:
                continue

            try:
                file_date = datetime.strptime(
                    match.group(1),
                    "%Y%m%d",
                ).replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                continue

            candidates.append(
                (
                    file_date,
                    filename,
                )
            )

        if candidates:
            candidates.sort(
                reverse=True
            )

            return (
                year,
                candidates[0][1],
            )

    raise RuntimeError(
        "Could not find any G10016 Version 4 Antarctic "
        "daily NetCDF files in the NSIDC HTTPS directory."
    )


def _download_file(
    url: str,
    destination: Path,
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with requests.get(
        url,
        headers=HEADERS,
        stream=True,
        timeout=60,
    ) as response:
        response.raise_for_status()

        content_length = response.headers.get(
            "Content-Length"
        )

        if content_length:
            try:
                if int(content_length) < 10_000:
                    raise RuntimeError(
                        "The NSIDC response is unexpectedly small; "
                        "it may be an error page rather than a NetCDF file."
                    )
            except ValueError:
                pass

        temporary = destination.with_suffix(
            destination.suffix + ".part"
        )

        with temporary.open(
            "wb"
        ) as file:
            for chunk in response.iter_content(
                chunk_size=1024 * 1024
            ):
                if chunk:
                    file.write(chunk)

        temporary.replace(
            destination
        )


def download_nsidc(
    product_short_name: str = DEFAULT_SHORT_NAME,
    product_version: str = DEFAULT_VERSION,
) -> str:
    if product_short_name.upper() != "G10016":
        raise ValueError(
            "This downloader is currently implemented specifically "
            "for the Antarctic G10016 Version 4 product."
        )

    if str(product_version) != "4":
        raise ValueError(
            "This downloader currently targets G10016 Version 4. "
            "Update the project after NSIDC publishes a newer version."
        )

    base_url = BASE_URL_TEMPLATE.format(
        short_name=product_short_name,
        version=product_version,
    )

    print(
        f"NSIDC target: "
        f"{product_short_name} Version {product_version}"
    )

    print(
        f"Source directory: {base_url}"
    )

    year, filename = _find_latest_file(
        base_url
    )

    file_url = urljoin(
        base_url,
        f"{year}/{filename}",
    )

    destination = RAW_DIR / filename

    print(
        f"Latest Antarctic file: {filename}"
    )

    print(
        f"Downloading: {file_url}"
    )

    _download_file(
        file_url,
        destination,
    )

    size_mb = (
        destination.stat().st_size
        / (
            1024 * 1024
        )
    )

    if size_mb < 0.01:
        destination.unlink(
            missing_ok=True
        )

        raise RuntimeError(
            "Downloaded file is empty or unexpectedly small."
        )

    print(
        f"Downloaded successfully: "
        f"{destination} "
        f"({size_mb:.2f} MB)"
    )

    return str(destination)


def main() -> None:
    short_name = os.getenv(
        "NSIDC_SHORT_NAME",
        DEFAULT_SHORT_NAME,
    )

    version = os.getenv(
        "NSIDC_VERSION",
        DEFAULT_VERSION,
    )

    downloaded = download_nsidc(
        short_name,
        version,
    )

    print("\nNext step:")
    print(
        "python backend\\data\\convert_nsidc_bundle.py"
    )

    print(
        f"\nSaved file:\n{downloaded}"
    )


if __name__ == "__main__":
    main()