from typing import Literal

from pydantic import BaseModel

from app.comparison.models import ApplicationData, ExtractedLabel


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class FieldResponse(BaseModel):
    field: str
    match_type: str
    expected: str | float
    found: str | float | None
    status: Literal["PASS", "FAIL"]


class VerificationResponse(BaseModel):
    overall_verdict: Literal["APPROVED", "NEEDS_REVIEW"]
    fields: list[FieldResponse]
    latency_ms: int


class VerifyResponse(BaseModel):
    verification: VerificationResponse
    extracted_label: ExtractedLabel
    latency_ms: int


class BatchItemInput(BaseModel):
    client_id: str
    image_index: int
    application_data: ApplicationData


class BatchSummary(BaseModel):
    passed: int
    needs_review: int
    total: int


class BatchItemResult(BaseModel):
    client_id: str
    filename: str | None = None
    status: Literal["COMPLETED", "FAILED"]
    verification: VerificationResponse | None = None
    extracted_label: ExtractedLabel | None = None
    latency_ms: int
    error: ErrorDetail | None = None


class BatchVerifyResponse(BaseModel):
    summary: BatchSummary
    results: list[BatchItemResult]
