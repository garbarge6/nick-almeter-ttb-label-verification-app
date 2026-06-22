import base64
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from app.comparison.models import ExtractedLabel
from app.vision.preprocessing import ImagePreprocessingError, preprocess_image
from app.vision.prompts import VISION_SYSTEM_PROMPT, VISION_USER_PROMPT

logger = logging.getLogger(__name__)


class VisionServiceError(RuntimeError):
    pass


class VisionServiceTimeout(VisionServiceError):
    pass


class VisionServiceValidationError(VisionServiceError):
    pass


class VisionServiceAuthError(VisionServiceError):
    pass


class VisionImageError(VisionServiceError):
    pass


@dataclass(frozen=True)
class VisionSettings:
    model: str = "gpt-4o-mini"
    timeout_seconds: float = 4.0
    image_max_side: int = 1200
    jpeg_quality: int = 76

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
    def __init__(self) -> None:
        self._client: Any | None = None
        self._timeout_seconds: float | None = None

    def _get_client(self, timeout_seconds: float) -> Any:
        if self._client is None or self._timeout_seconds != timeout_seconds:
            from openai import OpenAI

            self._client = OpenAI(timeout=timeout_seconds)
            self._timeout_seconds = timeout_seconds
        return self._client

    def extract_label(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        image_data_url: str,
        timeout_seconds: float,
    ) -> object:
        client = self._get_client(timeout_seconds)
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
        total_start = time.perf_counter()
        original_bytes = len(image_bytes)

        try:
            preprocess_start = time.perf_counter()
            image = preprocess_image(
                image_bytes,
                max_side=self.settings.image_max_side,
                jpeg_quality=self.settings.jpeg_quality,
            )
            preprocess_ms = _elapsed_ms(preprocess_start)
        except ImagePreprocessingError as exc:
            raise VisionImageError("Invalid or unsupported image.") from exc

        image_data_url = _build_image_data_url(image.content, image.media_type)

        try:
            vision_start = time.perf_counter()
            response = self.client.extract_label(
                model=self.settings.model,
                system_prompt=VISION_SYSTEM_PROMPT,
                user_prompt=VISION_USER_PROMPT,
                image_data_url=image_data_url,
                timeout_seconds=self.settings.timeout_seconds,
            )
            vision_ms = _elapsed_ms(vision_start)
        except TimeoutError as exc:
            raise VisionServiceTimeout("Vision model request timed out.") from exc
        except Exception as exc:
            class_name = exc.__class__.__name__
            if class_name in {"APITimeoutError", "TimeoutException"}:
                raise VisionServiceTimeout("Vision model request timed out.") from exc
            if class_name in {"AuthenticationError", "PermissionDeniedError"}:
                raise VisionServiceAuthError("Vision service is not configured or authorized.") from exc
            raise VisionServiceError("Vision model request failed.") from exc

        parsed = _coerce_extracted_label(response)
        total_ms = _elapsed_ms(total_start)
        logger.info(
            "vision_extract_completed",
            extra={
                "filename": filename,
                "model": self.settings.model,
                "timeout_seconds": self.settings.timeout_seconds,
                "preprocess_ms": preprocess_ms,
                "vision_ms": vision_ms,
                "total_ms": total_ms,
                "image_original_bytes": original_bytes,
                "image_processed_bytes": len(image.content),
                "image_original_size": image.original_size,
                "image_processed_size": image.processed_size,
            },
        )
        return parsed


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


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