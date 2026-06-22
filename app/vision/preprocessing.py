from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


@dataclass(frozen=True)
class PreprocessedImage:
    content: bytes
    media_type: str
    original_size: tuple[int, int]
    processed_size: tuple[int, int]


class ImagePreprocessingError(ValueError):
    pass


def preprocess_image(
    image_bytes: bytes,
    *,
    max_side: int = 1600,
    jpeg_quality: int = 82,
) -> PreprocessedImage:
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            original_size = image.size
            processed = ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ImagePreprocessingError("Image bytes could not be opened.") from exc

    if max(processed.size) > max_side:
        processed.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

    output = BytesIO()
    processed.save(output, format="JPEG", quality=jpeg_quality, optimize=True)

    return PreprocessedImage(
        content=output.getvalue(),
        media_type="image/jpeg",
        original_size=original_size,
        processed_size=processed.size,
    )
