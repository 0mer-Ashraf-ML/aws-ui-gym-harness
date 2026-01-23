"""Environment helpers for parsing configuration values safely."""

from __future__ import annotations

import os
from typing import Optional


def get_int_env(key: str, default: int) -> int:
    """Return an integer env value, tolerating missing or empty strings."""
    raw: Optional[str] = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def get_float_env(key: str, default: float) -> float:
    raw: Optional[str] = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default