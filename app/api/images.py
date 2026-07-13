import os

from fastapi import UploadFile

from app.api.errors import error_response
from app.api.schemas import ErrorDetail

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


async def read_batch_images(images: list[UploadFile]) -> list[tuple[UploadFile, bytes | None, ErrorDetail | None]]:
    if not images:
        raise error_response(400, "invalid_batch", "Please add at least one label image.")

    if len(images) > BATCH_MAX_ITEMS:
        raise error_response(413, "batch_too_large", f"Please upload no more than {BATCH_MAX_ITEMS} label images at once.")

    stored: list[tuple[UploadFile, bytes | None, ErrorDetail | None]] = []
    for image in images:
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            stored.append((image, None, ErrorDetail(code="invalid_file_type", message=INVALID_IMAGE_TYPE_MESSAGE)))
            continue

        if image.size is not None and image.size > MAX_IMAGE_BYTES:
            stored.append((image, None, ErrorDetail(code="image_too_large", message="Please upload an image smaller than 8 MB.")))
            continue

        image_bytes = await image.read(MAX_IMAGE_BYTES + 1)
        if not image_bytes:
            stored.append((image, image_bytes, ErrorDetail(code="invalid_image", message="Please upload a non-empty image file.")))
            continue

        if len(image_bytes) > MAX_IMAGE_BYTES:
            stored.append((image, None, ErrorDetail(code="image_too_large", message="Please upload an image smaller than 8 MB.")))
            continue

        stored.append((image, image_bytes, None))
    return stored


def validate_batch_image(image: UploadFile, image_bytes: bytes | None, prevalidated_error: ErrorDetail | None = None) -> ErrorDetail | None:
    if prevalidated_error is not None:
        return prevalidated_error
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        return ErrorDetail(code="invalid_file_type", message=INVALID_IMAGE_TYPE_MESSAGE)
    if not image_bytes:
        return ErrorDetail(code="invalid_image", message="Please upload a non-empty image file.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        return ErrorDetail(code="image_too_large", message="Please upload an image smaller than 8 MB.")
    return None
