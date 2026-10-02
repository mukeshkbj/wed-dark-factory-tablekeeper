"""API error type and canonical error codes (spec section 5)."""


class ApiError(Exception):
    def __init__(self, status, code, message=""):
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code


def malformed(msg="malformed request"):
    return ApiError(400, "malformed_request", msg)


def missing_key():
    return ApiError(400, "missing_idempotency_key",
                    "Idempotency-Key header required")


def unauthenticated(msg="unauthenticated"):
    return ApiError(401, "unauthenticated", msg)


def forbidden(msg="forbidden"):
    return ApiError(403, "forbidden", msg)


def not_found(msg="not found"):
    return ApiError(404, "not_found", msg)


def conflict(code, msg=""):
    return ApiError(409, code, msg)


def validation(msg="validation failed", code="validation_failed"):
    return ApiError(422, code, msg)


def err_body(exc):
    return {"error": {"code": exc.code, "message": exc.message}}
