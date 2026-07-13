import argparse
import json
import sys
import tempfile
import time
from pathlib import Path


import httpx
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.comparison.engine import GOVERNMENT_WARNING


def application_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "brand_name": "ACME WINE",
        "product_class": "Cabernet Sauvignon",
        "producer_name": "Acme Winery LLC",
        "country_of_origin": "USA",
        "abv": "45%",
        "net_contents": "750 mL",
        "government_warning": GOVERNMENT_WARNING,
    }
    data.update(overrides)
    return data


def post_verify(base_url: str, image_path: Path, application: dict[str, object]) -> tuple[float, httpx.Response]:
    start = time.perf_counter()
    with image_path.open("rb") as image_file:
        response = httpx.post(
            f"{base_url}/verify",
            data={"application_data": json.dumps(application)},
            files={"image": (image_path.name, image_file, "image/png")},
            timeout=60,
        )
    return (time.perf_counter() - start) * 1000, response


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (len(ordered) - 1) * percentile_value
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def verification_verdict(payload: dict[str, object]) -> object:
    verification = payload.get("verification", {})
    if isinstance(verification, dict):
        return verification.get("overall_verdict") or verification.get("verdict")
    return None


def make_blurry_copy(image_path: Path) -> Path:
    image = Image.open(image_path).convert("RGB").filter(ImageFilter.GaussianBlur(radius=2.5))
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    image.save(temp.name)
    return Path(temp.name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 6 checklist against a deployed URL.")
    parser.add_argument("base_url", help="Deployed base URL, e.g. https://example.onrender.com")
    parser.add_argument("image", type=Path, help="PNG/JPG/WebP sample label image")
    parser.add_argument("--runs", type=int, default=20, help="Valid single-label latency runs; use 20 or more for p95")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    image_path = args.image
    report: dict[str, object] = {}

    latencies = []
    api_latencies = []
    verdicts = []
    for _ in range(args.runs):
        wall_ms, response = post_verify(base_url, image_path, application_data())
        latencies.append(wall_ms)
        payload = response.json()
        verdicts.append(verification_verdict(payload))
        api_latencies.append(payload.get("latency_ms"))
    report["single_label_speed"] = {
        "runs": args.runs,
        "wall_ms": [round(value) for value in latencies],
        "wall_p50_ms": round(percentile(latencies, 0.50)),
        "wall_p95_ms": round(percentile(latencies, 0.95)),
        "wall_max_ms": round(max(latencies)),
        "api_latency_ms": api_latencies,
        "api_p50_ms": round(percentile([value for value in api_latencies if isinstance(value, int | float)], 0.50)),
        "api_p95_ms": round(percentile([value for value in api_latencies if isinstance(value, int | float)], 0.95)),
        "verdicts": verdicts,
        "under_5000_ms": max(latencies) < 5000,
    }

    mismatch_wall, mismatch = post_verify(base_url, image_path, application_data(brand_name="WRONG BRAND"))
    report["mismatch"] = {
        "status": mismatch.status_code,
        "wall_ms": round(mismatch_wall),
        "verdict": verification_verdict(mismatch.json()),
    }

    blurry_path = make_blurry_copy(image_path)
    try:
        blurry_wall, blurry = post_verify(base_url, blurry_path, application_data())
        report["imperfect_image"] = {
            "status": blurry.status_code,
            "wall_ms": round(blurry_wall),
            "readable_error": blurry.json().get("detail", {}).get("error", {}).get("message"),
            "verdict": verification_verdict(blurry.json()),
        }
    finally:
        blurry_path.unlink(missing_ok=True)

    wrong = httpx.post(
        f"{base_url}/verify",
        data={"application_data": json.dumps(application_data())},
        files={"image": ("bad.txt", b"hello", "text/plain")},
        timeout=30,
    )
    report["wrong_file_type"] = {"status": wrong.status_code, "body": wrong.json()}

    empty = httpx.post(f"{base_url}/verify", data={}, timeout=30)
    report["empty_submit"] = {"status": empty.status_code, "body": empty.json()}

    with image_path.open("rb") as first, image_path.open("rb") as second:
        batch = httpx.post(
            f"{base_url}/verify/batch",
            data={
                "items": json.dumps(
                    [
                        {"client_id": "one", "image_index": 0, "application_data": application_data()},
                        {"client_id": "two", "image_index": 1, "application_data": application_data(brand_name="WRONG BRAND")},
                        {"client_id": "three", "image_index": 2, "application_data": application_data()},
                    ]
                )
            },
            files=[
                ("images", ("one.png", first, "image/png")),
                ("images", ("two.png", second, "image/png")),
                ("images", ("bad.txt", b"hello", "text/plain")),
            ],
            timeout=90,
        )
    report["batch_summary"] = {"status": batch.status_code, "summary": batch.json().get("summary")}

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()