"""
Custom exception hierarchy for RADAR Pangan API.

These exceptions carry HTTP status codes so FastAPI exception handlers
can convert them to proper responses without repeating try/except in every route.

Usage:
    from src.api.errors import NotFoundError, ValidationError, ServiceUnavailableError

    raise NotFoundError("Komoditas tidak ditemukan")
    raise ValidationError("Province 'Bali' tidak dikenal")
    raise ServiceUnavailableError("Database tidak tersedia")

Unhandled AppError subclasses → global exception handler in main.py.
"""

from __future__ import annotations


class AppError(Exception):
    """Base application exception with HTTP status code.

    Attributes:
        status_code: HTTP status code (default 500).
        detail: Human-readable error message for the client.
        internal_message: Optional technical detail for logging (not exposed to client).
    """

    status_code: int = 500

    def __init__(self, detail: str, *, internal_message: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.internal_message = internal_message


class NotFoundError(AppError):
    """Resource not found. Maps to HTTP 404."""

    status_code = 404


class ValidationError(AppError):
    """Invalid input or business rule violation. Maps to HTTP 422."""

    status_code = 422


class ServiceUnavailableError(AppError):
    """Dependency unavailable (DB, ML server, external API). Maps to HTTP 503."""

    status_code = 503


class ConflictError(AppError):
    """Duplicate resource or conflicting state. Maps to HTTP 409."""

    status_code = 409
