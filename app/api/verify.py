import json
import logging
import traceback
from pathlib import Path
import time
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ValidationError

from app.comparison.engine import verify_label
from app.comparison.models import ApplicationData, ExtractedLabel, VerificationResult
from app.vision import (
    VisionImageError,
    VisionService,
    VisionServiceError,
    VisionServiceTimeout,
    VisionServiceValidationError,
)

logger = logging.getLogger(__name__)
router = APIRouter()
DEBUG_LOG_PATH = Path("logs/verify-debug.log")

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class VerifyResponse(BaseModel):
    verification: VerificationResult
    extracted_label: ExtractedLabel
    latency_ms: int


def get_vision_service() -> VisionService:
    return VisionService()


def error_response(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


def parse_application_data(raw_application_data: str) -> ApplicationData:
    try:
        payload = json.loads(raw_application_data)
    except json.JSONDecodeError as exc:
        raise error_response(
            400,
            "invalid_application_data",
            "Application data must be valid JSON.",
        ) from exc

    try:
        return ApplicationData.model_validate(payload)
    except ValidationError as exc:
        raise error_response(
            422,
            "invalid_application_data",
            "Some required application fields are missing or invalid.",
        ) from exc


async def read_valid_image(image: UploadFile) -> bytes:
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise error_response(
            400,
            "invalid_file_type",
            "Please upload a PNG, JPG, or WebP image.",
        )

    image_bytes = await image.read()
    if not image_bytes:
        raise error_response(
            400,
            "invalid_image",
            "Please upload a non-empty image file.",
        )

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise error_response(
            413,
            "image_too_large",
            "Please upload an image smaller than 8 MB.",
        )

    return image_bytes


def log_verify_finished(
    *,
    latency_ms: int,
    verdict: str | None = None,
    error_code: str | None = None,
    failures: list[str] | None = None,
) -> None:
    if error_code:
        logger.warning(
            "verify_failed",
            extra={"latency_ms": latency_ms, "error_code": error_code},
        )
        return

    logger.info(
        "verify_completed",
        extra={
            "latency_ms": latency_ms,
            "verdict": verdict,
            "field_failures": failures or [],
        },
    )


def log_exception_details(error_code: str, latency_ms: int, exc: Exception) -> None:
    DEBUG_LOG_PATH.parent.mkdir(exist_ok=True)
    debug_text = "\n".join(
        [
            "--- verify exception ---",
            f"error_code={error_code}",
            f"latency_ms={latency_ms}",
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        ]
    )
    logger.exception(
        "verify_exception",
        extra={"latency_ms": latency_ms, "error_code": error_code},
    )
    with DEBUG_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(debug_text)
        log_file.write("\n")

@router.post(
    "/verify",
    response_model=VerifyResponse,
    responses={
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)
async def verify(
    image: UploadFile = File(...),
    application_data: str = Form(...),
    vision_service: VisionService = Depends(get_vision_service),
) -> VerifyResponse:
    start = time.perf_counter()

    def elapsed_ms() -> int:
        return int((time.perf_counter() - start) * 1000)

    try:
        image_bytes = await read_valid_image(image)
        application = parse_application_data(application_data)
        extracted = vision_service.extract_label(image_bytes, filename=image.filename)
        verification = verify_label(application, extracted)
        latency_ms = elapsed_ms()
        failures = [field.field for field in verification.fields if field.status == "FAIL"]
        log_verify_finished(
            latency_ms=latency_ms,
            verdict=verification.verdict,
            failures=failures,
        )
        return VerifyResponse(
            verification=verification,
            extracted_label=extracted,
            latency_ms=latency_ms,
        )
    except HTTPException as exc:
        latency_ms = elapsed_ms()
        detail: Any = exc.detail
        code = detail.get("error", {}).get("code") if isinstance(detail, dict) else "http_error"
        log_verify_finished(latency_ms=latency_ms, error_code=code)
        raise
    except VisionImageError as exc:
        latency_ms = elapsed_ms()
        log_verify_finished(latency_ms=latency_ms, error_code="invalid_image")
        log_exception_details("invalid_image", latency_ms, exc)
        raise error_response(400, "invalid_image", "We could not read this image. Please try another photo.") from exc
    except VisionServiceTimeout as exc:
        latency_ms = elapsed_ms()
        log_verify_finished(latency_ms=latency_ms, error_code="vision_timeout")
        log_exception_details("vision_timeout", latency_ms, exc)
        raise error_response(504, "vision_timeout", "We could not read this image quickly enough. Please try another photo.") from exc
    except VisionServiceValidationError as exc:
        latency_ms = elapsed_ms()
        log_verify_finished(latency_ms=latency_ms, error_code="vision_invalid_response")
        log_exception_details("vision_invalid_response", latency_ms, exc)
        raise error_response(502, "vision_invalid_response", "We could not understand the label extraction result. Please try another photo.") from exc
    except VisionServiceError as exc:
        latency_ms = elapsed_ms()
        log_verify_finished(latency_ms=latency_ms, error_code="vision_service_error")
        log_exception_details("vision_service_error", latency_ms, exc)
        raise error_response(502, "vision_service_error", "The label reading service is unavailable. Please try again.") from exc
    except Exception as exc:
        latency_ms = elapsed_ms()
        log_verify_finished(latency_ms=latency_ms, error_code="internal_error")
        log_exception_details("internal_error", latency_ms, exc)
        raise error_response(500, "internal_error", "Something went wrong. Please try again.") from exc