"""Backward-compatible entry point for the project's smoke test."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from self_check import main  # noqa: E402


if __name__ == "__main__":
    main()
