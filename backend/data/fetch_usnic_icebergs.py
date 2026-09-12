"""Download the current USNIC Antarctic iceberg CSV from the official page."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PAGE_URL = "https://usicecenter.gov/Products/AntarcIcebergs"
RAW_DIR = Path(__file__).resolve().parent / "real" / "raw"
DEFAULT_OUTPUT = RAW_DIR / "usnic_antarctic_icebergs.csv"
HEADERS = {
    "User-Agent": "Antarctic-Navigator/1.0 (SIH26059 prototype)"
}


def find_csv_url(page_url: str = PAGE_URL) -> str:
    """Find the current CSV link from the official USNIC page."""
    response = requests.get(
        page_url,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    candidates: list[tuple[int, str]] = []

    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        text = " ".join(anchor.stripped_strings).strip().lower()
        full_url = urljoin(page_url, href)
        lower_url = full_url.lower()

        score = 0
        if text == "csv":
            score += 100
        elif "csv" in text:
            score += 50
        if lower_url.endswith(".csv"):
            score += 50
        elif ".csv" in lower_url:
            score += 20

        if score:
            candidates.append((score, full_url))

    if not candidates:
        raise RuntimeError(
            "USNIC's Antarctic Iceberg page did not expose a CSV link. "
            "If the site layout changed, set USNIC_CSV_URL to the current "
            "CSV URL and run this script again."
        )

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )
    return candidates[0][1]


def download_usnic(
    output_path: str | Path = DEFAULT_OUTPUT,
    csv_url: str | None = None,
) -> Path:
    url = (
        csv_url
        or os.getenv("USNIC_CSV_URL")
        or find_csv_url()
    )
    destination = Path(output_path)
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(f"USNIC source: {url}")
    print(f"Saving to: {destination}")

    with requests.get(
        url,
        headers=HEADERS,
        stream=True,
        timeout=60,
    ) as response:
        response.raise_for_status()
        temporary = destination.with_suffix(
            destination.suffix + ".part"
        )
        with temporary.open("wb") as handle:
            for chunk in response.iter_content(
                chunk_size=64 * 1024
            ):
                if chunk:
                    handle.write(chunk)
        temporary.replace(destination)

    if destination.stat().st_size == 0:
        destination.unlink(missing_ok=True)
        raise RuntimeError("USNIC CSV download was empty.")

    print(
        f"USNIC CSV downloaded successfully: {destination}"
    )
    return destination


if __name__ == "__main__":
    download_usnic()
