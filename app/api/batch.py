import asyncio
import json
import os
import time

from fastapi import UploadFile
from pydantic import ValidationError

from app.api.errors import VISION_EXCEPTIONS, classify_vision_exception, error_response
from app.api.images import BATCH_MAX_ITEMS, read_batch_images, validate_batch_image
from app.api.logging import log_batch_finished, log_exception_details
from app.api.responses import verification_response
from app.api.schemas import BatchItemInput, BatchItemResult, BatchSummary, BatchVerifyResponse, ErrorDetail
from app.comparison.engine import verify_label
from app.vision import VisionService

BATCH_CONCURRENCY_LIMIT = int(os.getenv("BATCH_CONCURRENCY_LIMIT", "3"))


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


async def process_batch_item(
    item: BatchItemInput,
    image_files: list[tuple[UploadFile, bytes | None, ErrorDetail | None]],
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

        image, image_bytes, prevalidated_error = image_files[item.image_index]
        filename = image.filename
        image_error = validate_batch_image(image, image_bytes, prevalidated_error)
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
        latency_ms = elapsed_ms()
        return BatchItemResult(
            client_id=item.client_id,
            filename=filename,
            status="COMPLETED",
            verification=verification_response(verification, latency_ms),
            extracted_label=extracted,
            latency_ms=latency_ms,
        )
    except VISION_EXCEPTIONS as exc:
        latency_ms = elapsed_ms()
        classification = classify_vision_exception(exc)
        if classification is None:
            raise
        _, error = classification
        log_exception_details(error.code, latency_ms, exc)
        return BatchItemResult(
            client_id=item.client_id,
            filename=filename,
            status="FAILED",
            latency_ms=latency_ms,
            error=error,
        )
    except Exception as exc:
        latency_ms = elapsed_ms()
        log_exception_details("internal_error", latency_ms, exc)
        return BatchItemResult(
            client_id=item.client_id,
            filename=filename,
            status="FAILED",
            latency_ms=latency_ms,
            error=ErrorDetail(code="internal_error", message="Something went wrong. Please try again."),
        )


async def verify_batch_items(
    raw_items: str,
    images: list[UploadFile],
    vision_service: VisionService,
) -> BatchVerifyResponse:
    start = time.perf_counter()
    batch_items = parse_batch_items(raw_items)
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
        and result.verification.overall_verdict == "APPROVED"
    )
    needs_review = sum(
        1
        for result in results
        if result.status == "COMPLETED"
        and result.verification is not None
        and result.verification.overall_verdict == "NEEDS_REVIEW"
    )
    log_batch_finished(
        latency_ms=latency_ms,
        total=len(results),
        passed=passed,
        needs_review=needs_review,
    )
    return BatchVerifyResponse(
        summary=BatchSummary(
            passed=passed,
            needs_review=needs_review,
            total=len(results),
        ),
        results=results,
    )
