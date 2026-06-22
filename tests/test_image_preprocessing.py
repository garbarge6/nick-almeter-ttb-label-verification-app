from io import BytesIO

import pytest
from PIL import Image

from app.vision.preprocessing import ImagePreprocessingError, preprocess_image


def make_image_bytes(size: tuple[int, int] = (2400, 1200), color: str = "white") -> bytes:
    image = Image.new("RGB", size, color=color)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_preprocessing_downsizes_and_reencodes_to_jpeg() -> None:
    image = preprocess_image(make_image_bytes(), max_side=1600, jpeg_quality=82)

    assert image.media_type == "image/jpeg"
    assert image.original_size == (2400, 1200)
    assert image.processed_size == (1600, 800)
    assert image.content.startswith(b"\xff\xd8")


def test_preprocessing_rejects_invalid_image_bytes() -> None:
    with pytest.raises(ImagePreprocessingError):
        preprocess_image(b"not an image")


def test_preprocessing_tuned_defaults_keep_image_smaller() -> None:
    image = preprocess_image(make_image_bytes(), max_side=1200, jpeg_quality=76)

    assert image.processed_size == (1200, 600)
    assert len(image.content) < len(make_image_bytes())