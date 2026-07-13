import asyncio
from functools import lru_cache
import json
import logging
import os
import traceback
from pathlib import Path
import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ValidationError

from app.comparison.engine import verify_label
from app.comparison.models import ApplicationData, ExtractedLabel, VerificationResult
from app.vision import (
    VisionImageError,
    VisionServiceAuthError,
    VisionService,
    VisionServiceError,
    VisionServiceTimeout,
    VisionServiceValidationError,
)

logger = logging.getLogger(__name__)
router = APIRouter()
DEBUG_LOG_PATH = Path("logs/verify-debug.log")

ALLOWED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/heic",
    "image/heif",
    "image/tiff",
    "image/gif",
    "image/bmp",
}
INVALID_IMAGE_TYPE_MESSAGE = "Please upload an image file."
MAX_IMAGE_BYTES = 8 * 1024 * 1024
BATCH_MAX_ITEMS = int(os.getenv("BATCH_MAX_ITEMS", "10"))
BATCH_CONCURRENCY_LIMIT = int(os.getenv("BATCH_CONCURRENCY_LIMIT", "3"))


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class VerifyResponse(BaseModel):
    verification: VerificationResult
    extracted_label: ExtractedLabel
    latency_ms: int


class BatchItemInput(BaseModel):
    client_id: str
    image_index: int
    application_data: ApplicationData


class BatchSummary(BaseModel):
    total: int
    passed: int
    needs_review: int
    failed_to_process: int
    latency_ms: int


class BatchItemResult(BaseModel):
    client_id: str
    filename: str | None = None
    status: Literal["COMPLETED", "FAILED"]
    verification: VerificationResult | None = None
    extracted_label: ExtractedLabel | None = None
    latency_ms: int
    error: ErrorDetail | None = None


class BatchVerifyResponse(BaseModel):
    summary: BatchSummary
    results: list[BatchItemResult]


@lru_cache(maxsize=1)
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


def parse_batch_items(raw_items: str) -> list[BatchItemInput]:
    try:
        payload = json.loads(raw_items)
    except json.JSONDecodeError as exc:
        raise error_response(400, "invalid_batch", "Batch items must be valid JSON.") from exc

    if not isinstance(payload, list):
        raise error_response(400, "invalid_batch", "Batch items must be a list.")

    if not payload:
        raise error_response(400, "invalid_batch", "Please add at least one label to check.")

    if len(payload) > BATCH_MAX_ITEMS:
        raise error_response(413, "batch_too_large", f"Please check no more than {BATCH_MAX_ITEMS} labels at once.")

    items: list[BatchItemInput] = []
    for item in payload:
        try:
            items.append(BatchItemInput.model_validate(item))
        except ValidationError as exc:
            raise error_response(422, "invalid_batch", "Each batch item needs an image and all application fields.") from exc

    return items


async def read_valid_image(image: UploadFile) -> bytes:
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise error_response(
            400,
            "invalid_file_type",
            INVALID_IMAGE_TYPE_MESSAGE,
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


async def read_batch_images(images: list[UploadFile]) -> list[tuple[UploadFile, bytes]]:
    if not images:
        raise error_response(400, "invalid_batch", "Please add at least one label image.")

    stored: list[tuple[UploadFile, bytes]] = []
    for image in images:
        stored.append((image, await image.read()))
    return stored


def validate_batch_image(image: UploadFile, image_bytes: bytes) -> ErrorDetail | None:
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        return ErrorDetail(code="invalid_file_type", message=INVALID_IMAGE_TYPE_MESSAGE)
    if not image_bytes:
        return ErrorDetail(code="invalid_image", message="Please upload a non-empty image file.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        return ErrorDetail(code="image_too_large", message="Please upload an image smaller than 8 MB.")
    return None


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
        extracted = await asyncio.to_thread(
            vision_service.extract_label,
            image_bytes,
            image.filename,
        )
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
    except VisionServiceAuthError as exc:
        latency_ms = elapsed_ms()
        log_verify_finished(latency_ms=latency_ms, error_code="vision_auth_error")
        log_exception_details("vision_auth_error", latency_ms, exc)
        raise error_response(502, "vision_auth_error", "The label reading service is not configured. Please check the API key.") from exc
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


async def process_batch_item(
    item: BatchItemInput,
    image_files: list[tuple[UploadFile, bytes]],
    vision_service: VisionService,
    semaphore: asyncio.Semaphore,
) -> BatchItemResult:
    start = time.perf_counter()

    def elapsed_ms() -> int:
        return int((time.perf_counter() - start) * 1000)

    filename: str | None = None
    try:
        if item.image_index < 0 or item.image_index >= len(image_files):
            return BatchItemResult(
                client_id=item.client_id,
                filename=None,
                status="FAILED",
                latency_ms=elapsed_ms(),
                error=ErrorDetail(code="missing_image", message="A label image is missing."),
            )

        image, image_bytes = image_files[item.image_index]
        filename = image.filename
        image_error = validate_batch_image(image, image_bytes)
        if image_error:
            return BatchItemResult(
                client_id=item.client_id,
                filename=filename,
                status="FAILED",
                latency_ms=elapsed_ms(),
                error=image_error,
            )

        async with semaphore:
            extracted = await asyncio.to_thread(
                vision_service.extract_label,
                image_bytes,
                filename,
            )
        verification = verify_label(item.application_data, extracted)
        return BatchItemResult(
            client_id=item.client_id,
            filename=filename,
            status="COMPLETED",
            verification=verification,
            extracted_label=extracted,
            latency_ms=elapsed_ms(),
        )
    except VisionServiceTimeout as exc:
        log_exception_details("vision_timeout", elapsed_ms(), exc)
        return BatchItemResult(
            client_id=item.client_id,
            filename=filename,
            status="FAILED",
            latency_ms=elapsed_ms(),
            error=ErrorDetail(code="vision_timeout", message="We could not read this image quickly enough. Please try another photo."),
        )
    except VisionImageError as exc:
        log_exception_details("invalid_image", elapsed_ms(), exc)
        return BatchItemResult(
            client_id=item.client_id,
            filename=filename,
            status="FAILED",
            latency_ms=elapsed_ms(),
            error=ErrorDetail(code="invalid_image", message="We could not read this image. Please try another photo."),
        )
    except VisionServiceValidationError as exc:
        log_exception_details("vision_invalid_response", elapsed_ms(), exc)
        return BatchItemResult(
            client_id=item.client_id,
            filename=filename,
            status="FAILED",
            latency_ms=elapsed_ms(),
            error=ErrorDetail(code="vision_invalid_response", message="We could not understand the label extraction result. Please try another photo."),
        )
    except VisionServiceAuthError as exc:
        log_exception_details("vision_auth_error", elapsed_ms(), exc)
        return BatchItemResult(
            client_id=item.client_id,
            filename=filename,
            status="FAILED",
            latency_ms=elapsed_ms(),
            error=ErrorDetail(code="vision_auth_error", message="The label reading service is not configured. Please check the API key."),
        )
    except VisionServiceError as exc:
        log_exception_details("vision_service_error", elapsed_ms(), exc)
        return BatchItemResult(
            client_id=item.client_id,
            filename=filename,
            status="FAILED",
            latency_ms=elapsed_ms(),
            error=ErrorDetail(code="vision_service_error", message="The label reading service is unavailable. Please try again."),
        )
    except Exception as exc:
        log_exception_details("internal_error", elapsed_ms(), exc)
        return BatchItemResult(
            client_id=item.client_id,
            filename=filename,
            status="FAILED",
            latency_ms=elapsed_ms(),
            error=ErrorDetail(code="internal_error", message="Something went wrong. Please try again."),
        )


@router.post(
    "/verify/batch",
    response_model=BatchVerifyResponse,
    responses={
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def verify_batch(
    items: str = Form(...),
    images: list[UploadFile] = File(...),
    vision_service: VisionService = Depends(get_vision_service),
) -> BatchVerifyResponse:
    start = time.perf_counter()
    batch_items = parse_batch_items(items)
    image_files = await read_batch_images(images)
    semaphore = asyncio.Semaphore(BATCH_CONCURRENCY_LIMIT)
    results = await asyncio.gather(
        *[process_batch_item(item, image_files, vision_service, semaphore) for item in batch_items]
    )
    latency_ms = int((time.perf_counter() - start) * 1000)
    passed = sum(
        1
        for result in results
        if result.status == "COMPLETED"
        and result.verification is not None
        and result.verification.verdict == "PASS"
    )
    needs_review = sum(
        1
        for result in results
        if result.status == "COMPLETED"
        and result.verification is not None
        and result.verification.verdict == "NEEDS_REVIEW"
    )
    failed_to_process = sum(1 for result in results if result.status == "FAILED")
    logger.info(
        "verify_batch_completed",
        extra={
            "latency_ms": latency_ms,
            "total": len(results),
            "passed": passed,
            "needs_review": needs_review,
            "failed_to_process": failed_to_process,
        },
    )
    return BatchVerifyResponse(
        summary=BatchSummary(
            total=len(results),
            passed=passed,
            needs_review=needs_review,
            failed_to_process=failed_to_process,
            latency_ms=latency_ms,
        ),
        results=results,
    )