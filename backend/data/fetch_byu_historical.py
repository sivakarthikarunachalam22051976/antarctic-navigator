"""Download and extract the current BYU/NIC consolidated iceberg archive."""
from __future__ import annotations

import os
import re
import shutil
import zipfile
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PAGE_URL = "https://www.scp.byu.edu/iceberg/database1.html"
HISTORICAL_ROOT = (
    Path(__file__).resolve().parent
    / "real"
    / "historical"
    / "byu_v8.0"
)
ZIP_PATH = HISTORICAL_ROOT.parent / "byu_consolidated_database_v8.0.zip"
HEADERS = {
    "User-Agent": "Antarctic-Navigator/1.0 (SIH26059 prototype)"
}


def find_database_url(page_url: str = PAGE_URL) -> str:
    response = requests.get(
        page_url,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    candidates: list[str] = []

    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        text = " ".join(anchor.stripped_strings).lower()
        full_url = urljoin(page_url, href)
        lower_url = full_url.lower()

        if (
            ("consolidated" in text and "8.0" in text)
            or re.search(r"consolidated_database_v8\.0\.zip$", lower_url)
        ):
            candidates.append(full_url)

    if not candidates:
        raise RuntimeError(
            "Could not find BYU/NIC consolidated database v8.0 on the "
            "official page. Set BYU_DATABASE_URL to the current ZIP URL "
            "and run again."
        )

    return candidates[0]


def download_and_extract(
    url: str | None = None,
) -> Path:
    source_url = (
        url
        or os.getenv("BYU_DATABASE_URL")
        or find_database_url()
    )

    ZIP_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(f"BYU/NIC source: {source_url}")
    print(f"Downloading to: {ZIP_PATH}")

    with requests.get(
        source_url,
        headers=HEADERS,
        stream=True,
        timeout=60,
    ) as response:
        response.raise_for_status()
        temporary = ZIP_PATH.with_suffix(
            ZIP_PATH.suffix + ".part"
        )
        with temporary.open("wb") as handle:
            for chunk in response.iter_content(
                chunk_size=64 * 1024
            ):
                if chunk:
                    handle.write(chunk)
        temporary.replace(ZIP_PATH)

    if ZIP_PATH.stat().st_size == 0:
        ZIP_PATH.unlink(missing_ok=True)
        raise RuntimeError("BYU/NIC database ZIP was empty.")

    if HISTORICAL_ROOT.exists():
        shutil.rmtree(HISTORICAL_ROOT)

    HISTORICAL_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    with zipfile.ZipFile(ZIP_PATH) as archive:
        archive.extractall(HISTORICAL_ROOT)

    print(
        f"Extracted BYU/NIC v8.0 to: {HISTORICAL_ROOT}"
    )
    return HISTORICAL_ROOT


if __name__ == "__main__":
    download_and_extract()
