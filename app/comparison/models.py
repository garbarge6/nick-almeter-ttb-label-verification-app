from typing import Literal

from pydantic import BaseModel


FieldStatus = Literal["PASS", "FAIL"]
Verdict = Literal["PASS", "NEEDS_REVIEW"]


class ApplicationData(BaseModel):
    brand_name: str
    product_class: str
    producer_name: str
    country_of_origin: str
    abv: str | float
    net_contents: str
    government_warning: str


class ExtractedLabel(BaseModel):
    brand_name: str | None = None
    product_class: str | None = None
    producer_name: str | None = None
    country_of_origin: str | None = None
    abv: str | float | None = None
    net_contents: str | None = None
    government_warning: str | None = None


class FieldResult(BaseModel):
    field: str
    status: FieldStatus
    application_value: str | float
    extracted_value: str | float | None
    normalized_application_value: str | float | None = None
    normalized_extracted_value: str | float | None = None
    score: float | None = None
    message: str


class VerificationResult(BaseModel):
    verdict: Verdict
    fields: list[FieldResult]
