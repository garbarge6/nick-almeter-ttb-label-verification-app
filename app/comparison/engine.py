from collections.abc import Callable

from app.comparison.models import ApplicationData, ExtractedLabel, FieldResult, VerificationResult
from app.comparison.normalizers import (
    normalize_country,
    normalize_text,
    parse_abv_percent,
    parse_net_contents_ml,
    token_set_ratio,
)


FUZZY_THRESHOLD = 85.0
ABV_TOLERANCE = 0.1
NET_CONTENTS_ML_TOLERANCE = 1.0
GOVERNMENT_WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)


def _missing_result(field: str, application_value: str | float, extracted_value: object) -> FieldResult:
    return FieldResult(
        field=field,
        status="FAIL",
        application_value=application_value,
        extracted_value=extracted_value if isinstance(extracted_value, str | float) else None,
        message="Extracted value is missing.",
    )


def _compare_fuzzy(field: str, application_value: str, extracted_value: str | None) -> FieldResult:
    if extracted_value is None or extracted_value == "":
        return _missing_result(field, application_value, extracted_value)

    normalized_application = normalize_text(application_value)
    normalized_extracted = normalize_text(extracted_value)
    score = token_set_ratio(application_value, extracted_value)
    status = "PASS" if score >= FUZZY_THRESHOLD else "FAIL"

    return FieldResult(
        field=field,
        status=status,
        application_value=application_value,
        extracted_value=extracted_value,
        normalized_application_value=normalized_application,
        normalized_extracted_value=normalized_extracted,
        score=score,
        message=f"Fuzzy score {score} with threshold {FUZZY_THRESHOLD}.",
    )


def compare_brand_name(application_value: str, extracted_value: str | None) -> FieldResult:
    return _compare_fuzzy("brand_name", application_value, extracted_value)


def compare_product_class(application_value: str, extracted_value: str | None) -> FieldResult:
    return _compare_fuzzy("product_class", application_value, extracted_value)


def compare_producer_name(application_value: str, extracted_value: str | None) -> FieldResult:
    return _compare_fuzzy("producer_name", application_value, extracted_value)


def compare_country_of_origin(application_value: str, extracted_value: str | None) -> FieldResult:
    if extracted_value is None or extracted_value == "":
        return _missing_result("country_of_origin", application_value, extracted_value)

    normalized_application = normalize_country(application_value)
    normalized_extracted = normalize_country(extracted_value)
    status = "PASS" if normalized_application == normalized_extracted else "FAIL"

    return FieldResult(
        field="country_of_origin",
        status=status,
        application_value=application_value,
        extracted_value=extracted_value,
        normalized_application_value=normalized_application,
        normalized_extracted_value=normalized_extracted,
        message="Country values match after synonym normalization."
        if status == "PASS"
        else "Country values differ after synonym normalization.",
    )


def compare_abv(application_value: str | float, extracted_value: str | float | None) -> FieldResult:
    if extracted_value is None or extracted_value == "":
        return _missing_result("abv", application_value, extracted_value)

    normalized_application = parse_abv_percent(application_value)
    normalized_extracted = parse_abv_percent(extracted_value)
    status = (
        "PASS"
        if normalized_application is not None
        and normalized_extracted is not None
        and abs(normalized_application - normalized_extracted) <= ABV_TOLERANCE
        else "FAIL"
    )

    return FieldResult(
        field="abv",
        status=status,
        application_value=application_value,
        extracted_value=extracted_value,
        normalized_application_value=normalized_application,
        normalized_extracted_value=normalized_extracted,
        message="ABV values match within tolerance."
        if status == "PASS"
        else "ABV values are missing, unparseable, or outside tolerance.",
    )


def compare_net_contents(application_value: str, extracted_value: str | None) -> FieldResult:
    if extracted_value is None or extracted_value == "":
        return _missing_result("net_contents", application_value, extracted_value)

    normalized_application = parse_net_contents_ml(application_value)
    normalized_extracted = parse_net_contents_ml(extracted_value)
    status = (
        "PASS"
        if normalized_application is not None
        and normalized_extracted is not None
        and abs(normalized_application - normalized_extracted) <= NET_CONTENTS_ML_TOLERANCE
        else "FAIL"
    )

    return FieldResult(
        field="net_contents",
        status=status,
        application_value=application_value,
        extracted_value=extracted_value,
        normalized_application_value=normalized_application,
        normalized_extracted_value=normalized_extracted,
        message="Net contents match after ml normalization."
        if status == "PASS"
        else "Net contents are missing, unparseable, or outside tolerance.",
    )


def compare_government_warning(application_value: str, extracted_value: str | None) -> FieldResult:
    if extracted_value is None:
        return _missing_result("government_warning", application_value, extracted_value)

    status = "PASS" if application_value == extracted_value else "FAIL"

    return FieldResult(
        field="government_warning",
        status=status,
        application_value=application_value,
        extracted_value=extracted_value,
        normalized_application_value=None,
        normalized_extracted_value=None,
        message="Government warning is an exact case-sensitive match."
        if status == "PASS"
        else "Government warning must match exactly, including case and punctuation.",
    )


def verify_label(application: ApplicationData, extracted: ExtractedLabel) -> VerificationResult:
    comparisons: list[Callable[[], FieldResult]] = [
        lambda: compare_brand_name(application.brand_name, extracted.brand_name),
        lambda: compare_product_class(application.product_class, extracted.product_class),
        lambda: compare_producer_name(application.producer_name, extracted.producer_name),
        lambda: compare_country_of_origin(application.country_of_origin, extracted.country_of_origin),
        lambda: compare_abv(application.abv, extracted.abv),
        lambda: compare_net_contents(application.net_contents, extracted.net_contents),
        lambda: compare_government_warning(
            application.government_warning, extracted.government_warning
        ),
    ]
    fields = [compare() for compare in comparisons]
    verdict = "NEEDS_REVIEW" if any(field.status == "FAIL" for field in fields) else "APPROVED"

    return VerificationResult(verdict=verdict, fields=fields)
