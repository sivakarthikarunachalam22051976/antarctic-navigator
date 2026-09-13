"""Check whether the local Copernicus CDS API credentials are configured."""
from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    env_key = os.getenv("CDSAPI_KEY", "").strip()
    rc = Path.home() / ".cdsapirc"

    if env_key:
        print("CDS_CONFIG_OK environment")
        print(f"CDSAPI_URL={'set' if os.getenv('CDSAPI_URL') else 'default'}")
        return

    if not rc.exists():
        print("CDS_CONFIG_MISSING")
        print(f"Expected config file: {rc}")
        raise SystemExit(1)

    text = rc.read_text(encoding="utf-8", errors="replace")
    has_url = any(line.strip().startswith("url:") and line.split(":", 1)[1].strip() for line in text.splitlines())
    has_key = any(line.strip().startswith("key:") and line.split(":", 1)[1].strip() for line in text.splitlines())

    if not (has_url and has_key):
        print("CDS_CONFIG_INCOMPLETE")
        print(f"Expected url/key entries in: {rc}")
        raise SystemExit(1)

    print("CDS_CONFIG_OK file")
    print(f"Config: {rc}")


if __name__ == "__main__":
    main()
