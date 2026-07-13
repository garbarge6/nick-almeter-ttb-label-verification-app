from io import BytesIO

import httpx
import pytest
from openai import APITimeoutError
from PIL import Image

from app.comparison.engine import GOVERNMENT_WARNING
from app.comparison.models import ExtractedLabel
from app.vision import (
    FakeVisionClient,
    VisionImageError,
    VisionService,
    VisionServiceError,
    VisionServiceTimeout,
    VisionServiceValidationError,
)
from app.vision.prompts import VISION_SYSTEM_PROMPT
from app.vision.service import VisionSettings


def make_label_image_bytes() -> bytes:
    image = Image.new("RGB", (900, 600), color="white")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class ParsedResponse:
    def __init__(self, output_parsed: object) -> None:
        self.output_parsed = output_parsed


class TimeoutClient:
    def extract_label(self, **kwargs: object) -> object:
        raise TimeoutError("too slow")


class OpenAITimeoutClient:
    def extract_label(self, **kwargs: object) -> object:
        del kwargs
        raise APITimeoutError(request=httpx.Request("POST", "https://api.openai.test"))

class FailureClient:
    def extract_label(self, **kwargs: object) -> object:
        raise RuntimeError("api unavailable")


def test_service_returns_extracted_label_from_structured_response() -> None:
    response = {
        "brand_name": "Acme Wine",
        "class_type": "Cabernet Sauvignon",
        "producer": "Acme Winery",
        "country_of_origin": "USA",
        "abv": "45% Alc./Vol. (90 Proof)",
        "net_contents": "750 mL",
        "government_warning": GOVERNMENT_WARNING,
    }
    fake = FakeVisionClient(response)
    service = VisionService(client=fake, settings=VisionSettings(model="test-model"))

    extracted = service.extract_label(make_label_image_bytes())

    assert extracted == ExtractedLabel(**response)
    assert fake.requests[0]["model"] == "test-model"
    assert str(fake.requests[0]["image_data_url"]).startswith("data:image/jpeg;base64,")


def test_non_label_image_can_return_all_none_without_throwing() -> None:
    fake = FakeVisionClient({})
    service = VisionService(client=fake)

    extracted = service.extract_label(make_label_image_bytes())

    assert extracted == ExtractedLabel()


def test_partial_blurry_response_returns_partial_data() -> None:
    fake = FakeVisionClient(
        {
            "brand_name": "Acme Wine",
            "government_warning": GOVERNMENT_WARNING,
        }
    )
    service = VisionService(client=fake)

    extracted = service.extract_label(make_label_image_bytes())

    assert extracted.brand_name == "Acme Wine"
    assert extracted.class_type is None
    assert extracted.government_warning == GOVERNMENT_WARNING


def test_government_warning_preserves_exact_extracted_text() -> None:
    misread = GOVERNMENT_WARNING.replace("ability", "abiiity")
    fake = FakeVisionClient({"government_warning": misread})
    service = VisionService(client=fake)

    extracted = service.extract_label(make_label_image_bytes())

    assert extracted.government_warning == misread


def test_malformed_structured_response_raises_validation_error() -> None:
    fake = FakeVisionClient({"brand_name": {"not": "a string"}})
    service = VisionService(client=fake)

    with pytest.raises(VisionServiceValidationError):
        service.extract_label(make_label_image_bytes())


def test_parsed_response_without_structured_data_raises_validation_error() -> None:
    fake = FakeVisionClient(ParsedResponse(output_parsed=None))
    service = VisionService(client=fake)

    with pytest.raises(VisionServiceValidationError):
        service.extract_label(make_label_image_bytes())


def test_timeout_raises_controlled_timeout_error() -> None:
    service = VisionService(client=TimeoutClient())

    with pytest.raises(VisionServiceTimeout):
        service.extract_label(make_label_image_bytes())


def test_openai_timeout_exception_raises_controlled_timeout_error() -> None:
    service = VisionService(client=OpenAITimeoutClient())

    with pytest.raises(VisionServiceTimeout):
        service.extract_label(make_label_image_bytes())

def test_api_failure_raises_controlled_service_error() -> None:
    service = VisionService(client=FailureClient())

    with pytest.raises(VisionServiceError):
        service.extract_label(make_label_image_bytes())


def test_invalid_image_bytes_raise_image_error() -> None:
    service = VisionService(client=FakeVisionClient({}))

    with pytest.raises(VisionImageError):
        service.extract_label(b"not an image")


def test_prompt_tells_model_to_copy_warning_verbatim() -> None:
    assert "copy only the government warning exactly as printed" in VISION_SYSTEM_PROMPT
    assert "Do not substitute the standard warning from memory" in VISION_SYSTEM_PROMPT

