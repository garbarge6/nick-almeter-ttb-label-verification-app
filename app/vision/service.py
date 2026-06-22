import base64
import os
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from app.comparison.models import ExtractedLabel
from app.vision.preprocessing import ImagePreprocessingError, preprocess_image
from app.vision.prompts import VISION_SYSTEM_PROMPT, VISION_USER_PROMPT


class VisionServiceError(RuntimeError):
    pass


class VisionServiceTimeout(VisionServiceError):
    pass


class VisionServiceValidationError(VisionServiceError):
    pass


class VisionImageError(VisionServiceError):
    pass


@dataclass(frozen=True)
class VisionSettings:
    model: str = "gpt-4o-mini"
    timeout_seconds: float = 4.0
    image_max_side: int = 1600
    jpeg_quality: int = 82

    @classmethod
    def from_env(cls) -> "VisionSettings":
        return cls(
            model=os.getenv("VISION_MODEL", cls.model),
            timeout_seconds=float(os.getenv("VISION_TIMEOUT_SECONDS", cls.timeout_seconds)),
            image_max_side=int(os.getenv("VISION_IMAGE_MAX_SIDE", cls.image_max_side)),
            jpeg_quality=int(os.getenv("VISION_JPEG_QUALITY", cls.jpeg_quality)),
        )


class VisionClientProtocol(Protocol):
    def extract_label(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        image_data_url: str,
        timeout_seconds: float,
    ) -> ExtractedLabel | dict[str, object] | object:
        pass


class OpenAIVisionClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    def extract_label(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        image_data_url: str,
        timeout_seconds: float,
    ) -> object:
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key, timeout=timeout_seconds)
        return client.responses.parse(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": user_prompt},
                        {
                            "type": "input_image",
                            "image_url": image_data_url,
                            "detail": "high",
                        },
                    ],
                },
            ],
            text_format=ExtractedLabel,
        )


class FakeVisionClient:
    def __init__(self, response: ExtractedLabel | dict[str, object] | object) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []

    def extract_label(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        image_data_url: str,
        timeout_seconds: float,
    ) -> ExtractedLabel | dict[str, object] | object:
        self.requests.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "image_data_url": image_data_url,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.response


class VisionService:
    def __init__(
        self,
        *,
        client: VisionClientProtocol | None = None,
        settings: VisionSettings | None = None,
    ) -> None:
        self.settings = settings or VisionSettings.from_env()
        self.client = client or OpenAIVisionClient()

    def extract_label(self, image_bytes: bytes, filename: str | None = None) -> ExtractedLabel:
        del filename

        try:
            image = preprocess_image(
                image_bytes,
                max_side=self.settings.image_max_side,
                jpeg_quality=self.settings.jpeg_quality,
            )
        except ImagePreprocessingError as exc:
            raise VisionImageError("Invalid or unsupported image.") from exc

        image_data_url = _build_image_data_url(image.content, image.media_type)

        try:
            response = self.client.extract_label(
                model=self.settings.model,
                system_prompt=VISION_SYSTEM_PROMPT,
                user_prompt=VISION_USER_PROMPT,
                image_data_url=image_data_url,
                timeout_seconds=self.settings.timeout_seconds,
            )
        except TimeoutError as exc:
            raise VisionServiceTimeout("Vision model request timed out.") from exc
        except Exception as exc:
            if exc.__class__.__name__ in {"APITimeoutError", "TimeoutException"}:
                raise VisionServiceTimeout("Vision model request timed out.") from exc
            raise VisionServiceError("Vision model request failed.") from exc

        return _coerce_extracted_label(response)


def _build_image_data_url(image_bytes: bytes, media_type: str) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _coerce_extracted_label(response: ExtractedLabel | dict[str, object] | object) -> ExtractedLabel:
    parsed = getattr(response, "output_parsed", response)

    try:
        if isinstance(parsed, ExtractedLabel):
            return parsed
        if isinstance(parsed, dict):
            return ExtractedLabel.model_validate(parsed)
    except ValidationError as exc:
        raise VisionServiceValidationError("Vision response did not match ExtractedLabel.") from exc

    raise VisionServiceValidationError("Vision response did not contain structured label data.")
