#!/usr/bin/env python3
"""
Quick health check for the DeskZen dev stack used by the harness.

Checks the UI mirror (port 3001) and the FastAPI backend (port 8765) via
host.docker.internal so this can be invoked from within harness containers.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Iterable, Tuple

import requests

DEFAULT_UI_BASE = "http://host.docker.internal:3001"
DEFAULT_API_BASE = "http://host.docker.internal:8765"


@dataclass
class CheckResult:
    name: str
    url: str
    ok: bool
    detail: str


def try_endpoints(base_url: str, paths: Iterable[str]) -> Tuple[bool, str, str]:
    """
    Try GET requests for each path until one succeeds.
    Returns (ok, attempted_url, detail).
    """
    base = base_url.rstrip("/")
    for path in paths:
        url = f"{base}{path}"
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            return True, url, f"HTTP {resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            detail = f"{exc.__class__.__name__}: {exc}"
        # keep trying other paths
    # If we got here, every attempt failed; detail contains last error.
    return False, url, detail


def check_ui(base_url: str) -> CheckResult:
    ok, url, detail = try_endpoints(base_url, ["/healthz", "/"])
    return CheckResult(name="DeskZen UI", url=url, ok=ok, detail=detail)


def check_backend(base_url: str) -> CheckResult:
    ok, url, detail = try_endpoints(base_url, ["/healthz", "/docs", "/openapi.json"])
    return CheckResult(name="DeskZen API", url=url, ok=ok, detail=detail)


def main() -> int:
    ui_base = DEFAULT_UI_BASE
    api_base = DEFAULT_API_BASE

    ui_result = check_ui(ui_base)
    api_result = check_backend(api_base)

    results = [ui_result, api_result]
    for result in results:
        status = "✅" if result.ok else "❌"
        print(f"{status} {result.name}: {result.url} --> {result.detail}")

    if all(r.ok for r in results):
        return 0

    print("\nOne or more DeskZen endpoints are unreachable. "
          "Start the dev stack via /Users/siddhantvajpai/Desktop/ui_gym/dev/docker-compose.yaml "
          "and ensure ports 3001 and 8765 are exposed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

