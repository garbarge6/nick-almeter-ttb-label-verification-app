import json
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.verify import get_vision_service
from app.comparison.engine import GOVERNMENT_WARNING
from app.comparison.models import ExtractedLabel
from app.main import app
from app.vision import (
    VisionImageError,
    VisionServiceError,
    VisionServiceTimeout,
    VisionServiceValidationError,
)


class FakeVisionService:
    def __init__(self, extracted: ExtractedLabel | None = None, error: Exception | None = None) -> None:
        self.extracted = extracted or matching_extracted_label()
        self.error = error
        self.calls: list[dict[str, object]] = []

    def extract_label(self, image_bytes: bytes, filename: str | None = None) -> ExtractedLabel:
        self.calls.append({"image_bytes": image_bytes, "filename": filename})
        if self.error:
            raise self.error
        return self.extracted


@pytest.fixture(autouse=True)
def clear_overrides() -> None:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def make_image_bytes() -> bytes:
    image = Image.new("RGB", (200, 120), color="white")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def application_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "brand_name": "ACME WINE",
        "product_class": "Cabernet Sauvignon",
        "producer_name": "Acme Winery LLC",
        "country_of_origin": "USA",
        "abv": "45%",
        "net_contents": "750 mL",
        "government_warning": GOVERNMENT_WARNING,
    }
    payload.update(overrides)
    return payload


def matching_extracted_label(**overrides: object) -> ExtractedLabel:
    payload: dict[str, object] = {
        "brand_name": "acme wine",
        "product_class": "cabernet sauvignon",
        "producer_name": "Acme Winery",
        "country_of_origin": "United States",
        "abv": "45% Alc./Vol. (90 Proof)",
        "net_contents": "750ml",
        "government_warning": GOVERNMENT_WARNING,
    }
    payload.update(overrides)
    return ExtractedLabel(**payload)


def post_verify(
    client: TestClient,
    *,
    application_data: dict[str, object] | str | None = None,
    image_bytes: bytes | None = None,
    filename: str = "label.png",
    content_type: str = "image/png",
):
    data = {}
    if application_data is not None:
        data["application_data"] = (
            application_data if isinstance(application_data, str) else json.dumps(application_data)
        )

    files = None
    if image_bytes is not None:
        files = {"image": (filename, image_bytes, content_type)}

    return client.post("/verify", data=data, files=files)


def override_vision(service: FakeVisionService) -> FakeVisionService:
    app.dependency_overrides[get_vision_service] = lambda: service
    return service


def test_verify_happy_path_returns_full_result_and_latency(client: TestClient) -> None:
    service = override_vision(FakeVisionService())

    response = post_verify(
        client,
        application_data=application_payload(),
        image_bytes=make_image_bytes(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verification"]["verdict"] == "PASS"
    assert len(body["verification"]["fields"]) == 7
    assert body["extracted_label"]["government_warning"] == GOVERNMENT_WARNING
    assert isinstance(body["latency_ms"], int)
    assert body["latency_ms"] >= 0
    assert len(service.calls) == 1
    assert service.calls[0]["filename"] == "label.png"
    assert service.calls[0]["image_bytes"]


def test_verify_failure_includes_expected_found_and_verdict(client: TestClient) -> None:
    override_vision(FakeVisionService(matching_extracted_label(brand_name="Different Brand")))

    response = post_verify(
        client,
        application_data=application_payload(),
        image_bytes=make_image_bytes(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verification"]["verdict"] == "NEEDS_REVIEW"
    brand = next(field for field in body["verification"]["fields"] if field["field"] == "brand_name")
    assert brand["status"] == "FAIL"
    assert brand["application_value"] == "ACME WINE"
    assert brand["extracted_value"] == "Different Brand"


def test_verify_warning_failure_surfaces_extracted_warning_text(client: TestClient) -> None:
    title_case = GOVERNMENT_WARNING.replace("GOVERNMENT WARNING:", "Government Warning:")
    override_vision(FakeVisionService(matching_extracted_label(government_warning=title_case)))

    response = post_verify(
        client,
        application_data=application_payload(),
        image_bytes=make_image_bytes(),
    )

    assert response.status_code == 200
    body = response.json()
    warning = next(
        field for field in body["verification"]["fields"] if field["field"] == "government_warning"
    )
    assert body["verification"]["verdict"] == "NEEDS_REVIEW"
    assert body["extracted_label"]["government_warning"] == title_case
    assert warning["status"] == "FAIL"
    assert warning["extracted_value"] == title_case


def test_bad_file_type_returns_readable_400(client: TestClient) -> None:
    override_vision(FakeVisionService())

    response = post_verify(
        client,
        application_data=application_payload(),
        image_bytes=b"hello",
        filename="label.txt",
        content_type="text/plain",
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": {
            "error": {
                "code": "invalid_file_type",
                "message": "Please upload a PNG, JPG, or WebP image.",
            }
        }
    }


def test_empty_image_returns_readable_400(client: TestClient) -> None:
    override_vision(FakeVisionService())

    response = post_verify(
        client,
        application_data=application_payload(),
        image_bytes=b"",
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "invalid_image"
    assert "non-empty image" in response.json()["detail"]["error"]["message"]


def test_missing_application_data_returns_4xx_not_500(client: TestClient) -> None:
    override_vision(FakeVisionService())

    response = post_verify(client, application_data=None, image_bytes=make_image_bytes())

    assert response.status_code == 422
    assert "Traceback" not in response.text


def test_malformed_application_data_returns_readable_400(client: TestClient) -> None:
    override_vision(FakeVisionService())

    response = post_verify(
        client,
        application_data="{not-json",
        image_bytes=make_image_bytes(),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == {
        "code": "invalid_application_data",
        "message": "Application data must be valid JSON.",
    }


def test_missing_required_application_field_returns_readable_422(client: TestClient) -> None:
    override_vision(FakeVisionService())
    payload = application_payload()
    del payload["brand_name"]

    response = post_verify(client, application_data=payload, image_bytes=make_image_bytes())

    assert response.status_code == 422
    assert response.json()["detail"]["error"]["code"] == "invalid_application_data"


def test_oversized_image_returns_413(client: TestClient) -> None:
    override_vision(FakeVisionService())
    image_bytes = b"0" * (8 * 1024 * 1024 + 1)

    response = post_verify(client, application_data=application_payload(), image_bytes=image_bytes)

    assert response.status_code == 413
    assert response.json()["detail"]["error"]["code"] == "image_too_large"


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (VisionImageError("bad image"), 400, "invalid_image"),
        (VisionServiceTimeout("slow"), 504, "vision_timeout"),
        (VisionServiceValidationError("bad response"), 502, "vision_invalid_response"),
        (VisionServiceError("down"), 502, "vision_service_error"),
        (RuntimeError("boom"), 500, "internal_error"),
    ],
)
def test_vision_errors_return_shaped_responses(
    client: TestClient,
    error: Exception,
    status_code: int,
    code: str,
) -> None:
    override_vision(FakeVisionService(error=error))

    response = post_verify(
        client,
        application_data=application_payload(),
        image_bytes=make_image_bytes(),
    )

    assert response.status_code == status_code
    assert response.json()["detail"]["error"]["code"] == code
    assert "Traceback" not in response.text