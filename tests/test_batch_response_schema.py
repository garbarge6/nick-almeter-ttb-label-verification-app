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
            product_class="cabernet sauvignon",
            producer_name="Acme Winery",
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
        "product_class": "Cabernet Sauvignon",
        "producer_name": "Acme Winery LLC",
        "country_of_origin": "USA",
        "abv": "45%",
        "net_contents": "750 mL",
        "government_warning": GOVERNMENT_WARNING,
    }


def batch_items(count: int) -> list[dict[str, object]]:
    return [
        {
            "client_id": f"label-{index + 1}",
            "image_index": index,
            "application_data": application_payload(),
        }
        for index in range(count)
    ]


def image_files(count: int) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        ("images", (f"label-{index + 1}.png", make_image_bytes(), "image/png"))
        for index in range(count)
    ]


def setup_function() -> None:
    app.dependency_overrides.clear()


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_batch_summary_schema_literals_are_pinned() -> None:
    app.dependency_overrides[get_vision_service] = lambda: FakeVisionService()
    client = TestClient(app)

    response = client.post(
        "/verify/batch",
        data={"items": json.dumps(batch_items(2))},
        files=image_files(2),
    )

    assert response.status_code == 200
    assert set(response.json()["summary"]) == {"passed", "needs_review", "total"}