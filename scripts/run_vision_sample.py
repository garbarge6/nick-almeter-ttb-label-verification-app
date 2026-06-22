import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.comparison.engine import GOVERNMENT_WARNING
from app.vision import FakeVisionClient, VisionService


FAKE_RESPONSE = {
    "brand_name": "Acme Wine",
    "product_class": "Cabernet Sauvignon",
    "producer_name": "Acme Winery",
    "country_of_origin": "USA",
    "abv": "45% Alc./Vol. (90 Proof)",
    "net_contents": "750 mL",
    "government_warning": GOVERNMENT_WARNING,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract label fields from one sample image.")
    parser.add_argument("image", type=Path, help="Path to a sample label image.")
    parser.add_argument(
        "--fake",
        action="store_true",
        help="Use a fake VisionService client for offline smoke checks.",
    )
    args = parser.parse_args()

    image_bytes = args.image.read_bytes()
    client = FakeVisionClient(FAKE_RESPONSE) if args.fake else None
    extracted = VisionService(client=client).extract_label(image_bytes, filename=args.image.name)
    print(json.dumps(extracted.model_dump(), indent=2))


if __name__ == "__main__":
    main()