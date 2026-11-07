import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.config import settings

logger = logging.getLogger("veritas.exceptions")


class VeritasException(Exception):
    """Base structured exception for VERITAS AI backend operations."""

    def __init__(
        self,
        message: str,
        code: str = "VERITAS_INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class AuthenticationException(VeritasException):
    def __init__(
        self,
        message: str = "Authentication required to access this forensic resource.",
        code: str = "AUTHENTICATION_REQUIRED",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details or {},
        )


class AuthorizationException(VeritasException):
    def __init__(
        self,
        message: str = "Insufficient role permissions or investigation access denied.",
        code: str = "ACCESS_DENIED",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details or {},
        )


class RateLimitException(VeritasException):
    def __init__(
        self,
        message: str = "Too many attempts. Please wait before retrying.",
        code: str = "RATE_LIMIT_EXCEEDED",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details or {},
        )


class ResourceNotFoundException(VeritasException):
    def __init__(self, resource: str, identifier: Any) -> None:
        super().__init__(
            message=f"{resource} with identifier '{identifier}' was not found.",
            code="RESOURCE_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"resource": resource, "identifier": str(identifier)},
        )


class DatabaseOperationException(VeritasException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="DATABASE_OPERATION_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details or {},
        )


class InvalidDocumentException(VeritasException):
    def __init__(
        self,
        message: str,
        code: str = "INVALID_DOCUMENT_PAYLOAD",
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status_code,
            details=details or {},
        )


def _error_payload(
    code: str,
    message: str,
    details: Optional[Any] = None,
    path: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "status": "error",
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "path": path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(VeritasException)
    async def veritas_exception_handler(
        request: Request, exc: VeritasException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(
                code=exc.code,
                message=exc.message,
                details=exc.details,
                path=request.url.path,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(
                code=f"HTTP_{exc.status_code}",
                message=str(exc.detail),
                path=request.url.path,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_payload(
                code="VALIDATION_ERROR",
                message="Request payload failed schema validation.",
                details={"errors": exc.errors()},
                path=request.url.path,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled exception on %s", request.url.path)
        safe_details: Dict[str, Any] = {}
        if settings.debug and not settings.is_production:
            safe_details = {"type": exc.__class__.__name__}
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_payload(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected server error occurred. The incident has been logged.",
                details=safe_details,
                path=request.url.path,
            ),
        )
