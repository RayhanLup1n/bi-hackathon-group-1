"""
Check PIHPS API availability (fail-fast health check).

Used by Kestra daily pipeline as first step to verify
the data source is reachable before running extraction.

Usage:
    python etl/scripts/check_pihps_health.py
"""
from __future__ import annotations

import sys

try:
    import httpx
except ImportError:
    print("ERROR: httpx package not installed")
    sys.exit(1)


def main() -> None:
    url = "https://www.bi.go.id/hargapangan"
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        print(f"PIHPS accessible: HTTP {resp.status_code}")
    except httpx.ConnectError:
        print(f"ERROR: Cannot connect to {url}")
        sys.exit(1)
    except httpx.HTTPStatusError as exc:
        print(f"ERROR: PIHPS returned HTTP {exc.response.status_code}")
        sys.exit(1)
    except httpx.TimeoutException:
        print(f"ERROR: PIHPS timeout after 15s")
        sys.exit(1)


if __name__ == "__main__":
    main()
