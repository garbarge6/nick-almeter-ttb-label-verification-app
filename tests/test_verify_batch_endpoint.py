import json
import threading
import time
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.api.verify import get_vision_service
from app.comparison.engine import GOVERNMENT_WARNING
from app.comparison.models import ExtractedLabel
from app.main import app


class BatchFakeVisionService:
    def __init__(self, responses: list[ExtractedLabel], delay: float = 0.0) -> None:
        self.responses = responses
        self.delay = delay
        self.calls: list[str | None] = []
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def extract_label(self, image_bytes: bytes, filename: str | None = None) -> ExtractedLabel:
        del image_bytes
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            index = len(self.calls)
            self.calls.append(filename)
        try:
            if self.delay:
                time.sleep(self.delay)
            return self.responses[min(index, len(self.responses) - 1)]
        finally:
            with self.lock:
                self.active -= 1


def make_image_bytes() -> bytes:
    image = Image.new("RGB", (120, 80), color="white")
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


def extracted_label(**overrides: object) -> ExtractedLabel:
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


def batch_items(count: int) -> list[dict[str, object]]:
    return [
        {
            "client_id": f"label-{index + 1}",
            "image_index": index,
            "application_data": application_payload(),
        }
        for index in range(count)
    ]


def post_batch(client: TestClient, items: object, files: list[tuple[str, tuple[str, bytes, str]]]):
    return client.post("/verify/batch", data={"items": json.dumps(items)}, files=files)


def image_files(count: int) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        ("images", (f"label-{index + 1}.png", make_image_bytes(), "image/png"))
        for index in range(count)
    ]


def setup_function() -> None:
    app.dependency_overrides.clear()


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_batch_all_pass_summary_and_item_results() -> None:
    service = BatchFakeVisionService([extracted_label(), extracted_label(), extracted_label()])
    app.dependency_overrides[get_vision_service] = lambda: service
    client = TestClient(app)

    response = post_batch(client, batch_items(3), image_files(3))

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total"] == 3
    assert body["summary"]["passed"] == 3
    assert body["summary"]["needs_review"] == 0
    assert body["summary"]["failed_to_process"] == 0
    assert isinstance(body["summary"]["latency_ms"], int)
    assert [result["client_id"] for result in body["results"]] == ["label-1", "label-2", "label-3"]
    assert all(result["status"] == "COMPLETED" for result in body["results"])
    assert all(result["verification"]["verdict"] == "PASS" for result in body["results"])
    assert len(service.calls) == 3


def test_batch_mixed_summary_counts_and_expected_found() -> None:
    service = BatchFakeVisionService(
        [
            extracted_label(),
            extracted_label(brand_name="Different Brand"),
            extracted_label(),
        ]
    )
    app.dependency_overrides[get_vision_service] = lambda: service
    client = TestClient(app)
    files = image_files(2) + [("images", ("bad.txt", b"hello", "text/plain"))]

    response = post_batch(client, batch_items(3), files)

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "total": 3,
        "passed": 1,
        "needs_review": 1,
        "failed_to_process": 1,
        "latency_ms": body["summary"]["latency_ms"],
    }
    assert body["results"][0]["verification"]["verdict"] == "PASS"
    assert body["results"][1]["verification"]["verdict"] == "NEEDS_REVIEW"
    brand = next(
        field for field in body["results"][1]["verification"]["fields"] if field["field"] == "brand_name"
    )
    assert brand["application_value"] == "ACME WINE"
    assert brand["extracted_value"] == "Different Brand"
    assert body["results"][2]["status"] == "FAILED"
    assert body["results"][2]["error"]["code"] == "invalid_file_type"
    assert len(service.calls) == 2


def test_batch_one_missing_image_does_not_fail_whole_batch() -> None:
    service = BatchFakeVisionService([extracted_label()])
    app.dependency_overrides[get_vision_service] = lambda: service
    client = TestClient(app)
    items = batch_items(2)
    items[1]["image_index"] = 5

    response = post_batch(client, items, image_files(1))

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["passed"] == 1
    assert body["summary"]["failed_to_process"] == 1
    assert body["results"][1]["error"]["code"] == "missing_image"


def test_batch_malformed_items_returns_readable_400() -> None:
    app.dependency_overrides[get_vision_service] = lambda: BatchFakeVisionService([extracted_label()])
    client = TestClient(app)

    response = client.post("/verify/batch", data={"items": "{not-json"}, files=image_files(1))

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == {
        "code": "invalid_batch",
        "message": "Batch items must be valid JSON.",
    }


def test_batch_larger_than_max_returns_readable_413() -> None:
    app.dependency_overrides[get_vision_service] = lambda: BatchFakeVisionService([extracted_label()])
    client = TestClient(app)

    response = post_batch(client, batch_items(11), image_files(1))

    assert response.status_code == 413
    assert response.json()["detail"]["error"]["code"] == "batch_too_large"


def test_batch_processes_items_concurrently_with_fake_slow_service() -> None:
    service = BatchFakeVisionService([extracted_label(), extracted_label(), extracted_label()], delay=0.15)
    app.dependency_overrides[get_vision_service] = lambda: service
    client = TestClient(app)

    response = post_batch(client, batch_items(3), image_files(3))

    assert response.status_code == 200
    assert service.max_active > 1
    assert service.max_active <= 3