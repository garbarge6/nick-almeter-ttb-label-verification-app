from app.api.schemas import FieldResponse, VerificationResponse
from app.comparison.models import FieldResult, VerificationResult


def field_response(field: FieldResult) -> FieldResponse:
    return FieldResponse(
        field=field.field,
        match_type=field.match_type,
        expected=field.expected,
        found=field.found,
        status=field.status,
    )


def verification_response(verification: VerificationResult, latency_ms: int) -> VerificationResponse:
    return VerificationResponse(
        overall_verdict=verification.overall_verdict,
        fields=[field_response(field) for field in verification.fields],
        latency_ms=latency_ms,
    )
