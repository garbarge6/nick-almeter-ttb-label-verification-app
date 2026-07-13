from typing import Literal

from pydantic import BaseModel, field_validator


FieldStatus = Literal["PASS", "FAIL"]
MatchType = Literal["fuzzy", "synonym", "numeric", "unit", "exact"]
Verdict = Literal["APPROVED", "NEEDS_REVIEW"]


class ApplicationData(BaseModel):
    brand_name: str
    class_type: str
    producer: str
    country_of_origin: str
    abv: str | float
    net_contents: str
    government_warning: str

    @field_validator(
        "brand_name",
        "class_type",
        "producer",
        "country_of_origin",
        "abv",
        "net_contents",
        "government_warning",
    )
    @classmethod
    def required_fields_must_not_be_blank(cls, value: str | float) -> str | float:
        if isinstance(value, str) and not value.strip():
            raise ValueError("Field is required.")
        return value


class ExtractedLabel(BaseModel):
    brand_name: str | None = None
    class_type: str | None = None
    producer: str | None = None
    country_of_origin: str | None = None
    abv: str | float | None = None
    net_contents: str | None = None
    government_warning: str | None = None
    raw_text: str | None = None
    extraction_confidence: float | None = None


class FieldDetails(BaseModel):
    normalized_expected: str | float | None = None
    normalized_found: str | float | None = None
    score: float | None = None
    message: str | None = None


class FieldResult(BaseModel):
    field: str
    match_type: MatchType
    expected: str | float
    found: str | float | None
    status: FieldStatus
    details: FieldDetails | None = None


class VerificationResult(BaseModel):
    overall_verdict: Verdict
    fields: list[FieldResult]
    latency_ms: int

