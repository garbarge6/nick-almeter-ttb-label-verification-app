import asyncio
from functools import lru_cache
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from app.api.batch import verify_batch_items
from app.api.errors import VISION_EXCEPTIONS, classify_vision_exception, error_response
from app.api.images import read_valid_image
from app.api.logging import log_exception_details, log_verify_finished
from app.api.responses import verification_response
from app.api.schemas import BatchVerifyResponse, ErrorResponse, VerifyResponse
from app.comparison.engine import verify_label
from app.comparison.models import ApplicationData
from app.vision import VisionService

router = APIRouter()


@lru_cache(maxsize=1)
def get_vision_service() -> VisionService:
    return VisionService()


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
            verdict=verification.overall_verdict,
            failures=failures,
        )
        return VerifyResponse(
            verification=verification_response(verification, latency_ms),
            extracted_label=extracted,
            latency_ms=latency_ms,
        )
    except HTTPException as exc:
        latency_ms = elapsed_ms()
        detail: Any = exc.detail
        code = detail.get("error", {}).get("code") if isinstance(detail, dict) else "http_error"
        log_verify_finished(latency_ms=latency_ms, error_code=code)
        raise
    except VISION_EXCEPTIONS as exc:
        latency_ms = elapsed_ms()
        classification = classify_vision_exception(exc)
        if classification is None:
            raise
        status_code, error = classification
        log_verify_finished(latency_ms=latency_ms, error_code=error.code)
        log_exception_details(error.code, latency_ms, exc)
        raise error_response(status_code, error.code, error.message) from exc
    except Exception as exc:
        latency_ms = elapsed_ms()
        log_verify_finished(latency_ms=latency_ms, error_code="internal_error")
        log_exception_details("internal_error", latency_ms, exc)
        raise error_response(500, "internal_error", "Something went wrong. Please try again.") from exc


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
    return await verify_batch_items(items, images, vision_service)
