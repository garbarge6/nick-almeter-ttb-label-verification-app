import json
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.api.verify import get_vision_service
from app.comparison.engine import GOVERNMENT_WARNING
from app.comparison.models import ExtractedLabel
from app.main import app


class FakeVisionService:
    def extract_label(self, image_bytes: bytes, filename: str | None = None) -> ExtractedLabel:
        del image_bytes, filename
        return ExtractedLabel(
            brand_name="acme wine",
            class_type="cabernet sauvignon",
            producer="Acme Winery",
            country_of_origin="United States",
            abv="45% Alc./Vol. (90 Proof)",
            net_contents="750ml",
            government_warning=GOVERNMENT_WARNING,
            raw_text="ACME WINE Cabernet Sauvignon",
            extraction_confidence=0.97,
        )


def make_image_bytes() -> bytes:
    image = Image.new("RGB", (120, 80), color="white")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def application_payload() -> dict[str, object]:
    return {
        "brand_name": "ACME WINE",
        "class_type": "Cabernet Sauvignon",
        "producer": "Acme Winery LLC",
        "country_of_origin": "USA",
        "abv": "45%",
        "net_contents": "750 mL",
        "government_warning": GOVERNMENT_WARNING,
    }


def setup_function() -> None:
    app.dependency_overrides.clear()


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_verify_response_schema_literals_are_pinned() -> None:
    app.dependency_overrides[get_vision_service] = lambda: FakeVisionService()
    client = TestClient(app)

    response = client.post(
        "/verify",
        data={"application_data": json.dumps(application_payload())},
        files={"image": ("label.png", make_image_bytes(), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    verification = body["verification"]
    assert verification["overall_verdict"] in {"APPROVED", "NEEDS_REVIEW"}
    assert verification["overall_verdict"] != "PASS"
    assert "latency_ms" in verification

    expected_field_keys = {"field", "match_type", "expected", "found", "status"}
    for field in verification["fields"]:
        assert set(field) == expected_field_keys
        assert field["status"] in {"PASS", "FAIL"}

    assert "raw_text" in body["extracted_label"]
    assert "extraction_confidence" in body["extracted_label"]

