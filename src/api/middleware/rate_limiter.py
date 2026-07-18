"""Rate limiter configuration for RADAR Pangan API.

Uses slowapi with in-memory storage — sufficient for single-worker Railway deployment.
ponytail: swap to Redis backend (slowapi[redis]) if scaling to multi-worker.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Global default: 100 requests per minute per IP
# Override per-endpoint via @limiter.limit() decorator or router-level limits
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    headers_enabled=True,  # X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
)
