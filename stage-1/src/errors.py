"""Error envelope (spec section 5).

Every 4xx/5xx response carries `{"error": {"code": ..., "message": ...}}`.
The HTTP status and `code` are contractual; `message` wording is free.

Owned by the engineer seat.
"""
from __future__ import annotations


class ApiError(Exception):
    """An error that maps directly onto an HTTP error response."""

    def __init__(self, status: int, code: str, message: str = ""):
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code

    def body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}
