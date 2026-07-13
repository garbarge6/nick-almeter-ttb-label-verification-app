from fastapi import HTTPException

from app.api.schemas import ErrorDetail
from app.vision import (
    VisionImageError,
    VisionServiceAuthError,
    VisionServiceError,
    VisionServiceTimeout,
    VisionServiceValidationError,
)

VisionException = (
    VisionImageError
    | VisionServiceTimeout
    | VisionServiceValidationError
    | VisionServiceAuthError
    | VisionServiceError
)

VISION_EXCEPTIONS = (
    VisionImageError,
    VisionServiceTimeout,
    VisionServiceValidationError,
    VisionServiceAuthError,
    VisionServiceError,
)

VISION_ERROR_MAP: dict[type[Exception], tuple[int, str, str]] = {
    VisionImageError: (
        400,
        "invalid_image",
        "We could not read this image. Please try another photo.",
    ),
    VisionServiceTimeout: (
        504,
        "vision_timeout",
        "We could not read this image quickly enough. Please try another photo.",
    ),
    VisionServiceValidationError: (
        502,
        "vision_invalid_response",
        "We could not understand the label extraction result. Please try another photo.",
    ),
    VisionServiceAuthError: (
        502,
        "vision_auth_error",
        "The label reading service is not configured. Please check the API key.",
    ),
    VisionServiceError: (
        502,
        "vision_service_error",
        "The label reading service is unavailable. Please try again.",
    ),
}


def error_response(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


def classify_vision_exception(exc: Exception) -> tuple[int, ErrorDetail] | None:
    for exc_type, (status, code, message) in VISION_ERROR_MAP.items():
        if isinstance(exc, exc_type):
            return status, ErrorDetail(code=code, message=message)
    return None
