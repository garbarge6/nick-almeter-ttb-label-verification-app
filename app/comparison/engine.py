from collections.abc import Callable
import re
import time

from app.comparison.models import ApplicationData, ExtractedLabel, FieldDetails, FieldResult, VerificationResult
from app.comparison.normalizers import (
    normalize_country,
    normalize_text,
    parse_abv_percent,
    parse_net_contents_ml,
    token_set_ratio,
)


FUZZY_THRESHOLD = 90.0
ABV_TOLERANCE = 0.1
NET_CONTENTS_ML_TOLERANCE = 1.0
GOVERNMENT_WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _missing_result(field: str, match_type: str, expected: str | float, found: object) -> FieldResult:
    return FieldResult(
        field=field,
        match_type=match_type,
        expected=expected,
        found=found if isinstance(found, str | float) else None,
        status="FAIL",
        details=FieldDetails(message="Extracted value is missing."),
    )


def _compare_fuzzy(field: str, expected: str, found: str | None) -> FieldResult:
    if found is None or found == "":
        return _missing_result(field, "fuzzy", expected, found)

    normalized_expected = normalize_text(expected)
    normalized_found = normalize_text(found)
    score = token_set_ratio(expected, found)
    status = "PASS" if score >= FUZZY_THRESHOLD else "FAIL"

    return FieldResult(
        field=field,
        match_type="fuzzy",
        expected=expected,
        found=found,
        status=status,
        details=FieldDetails(
            normalized_expected=normalized_expected,
            normalized_found=normalized_found,
            score=score,
            message=f"Fuzzy score {score} with threshold {FUZZY_THRESHOLD}.",
        ),
    )


def compare_brand_name(expected: str, found: str | None) -> FieldResult:
    return _compare_fuzzy("brand_name", expected, found)


def compare_class_type(expected: str, found: str | None) -> FieldResult:
    return _compare_fuzzy("class_type", expected, found)



def compare_producer(expected: str, found: str | None) -> FieldResult:
    return _compare_fuzzy("producer", expected, found)



def compare_country_of_origin(expected: str, found: str | None) -> FieldResult:
    if found is None or found == "":
        return _missing_result("country_of_origin", "synonym", expected, found)

    normalized_expected = normalize_country(expected)
    normalized_found = normalize_country(found)
    status = "PASS" if normalized_expected == normalized_found else "FAIL"

    return FieldResult(
        field="country_of_origin",
        match_type="synonym",
        expected=expected,
        found=found,
        status=status,
        details=FieldDetails(
            normalized_expected=normalized_expected,
            normalized_found=normalized_found,
            message="Country values match after synonym normalization."
            if status == "PASS"
            else "Country values differ after synonym normalization.",
        ),
    )


def compare_abv(expected: str | float, found: str | float | None) -> FieldResult:
    if found is None or found == "":
        return _missing_result("abv", "numeric", expected, found)

    normalized_expected = parse_abv_percent(expected)
    normalized_found = parse_abv_percent(found)
    status = (
        "PASS"
        if normalized_expected is not None
        and normalized_found is not None
        and abs(normalized_expected - normalized_found) <= ABV_TOLERANCE
        else "FAIL"
    )

    return FieldResult(
        field="abv",
        match_type="numeric",
        expected=expected,
        found=found,
        status=status,
        details=FieldDetails(
            normalized_expected=normalized_expected,
            normalized_found=normalized_found,
            message="ABV values match within tolerance."
            if status == "PASS"
            else "ABV values are missing, unparseable, or outside tolerance.",
        ),
    )


def compare_net_contents(expected: str, found: str | None) -> FieldResult:
    if found is None or found == "":
        return _missing_result("net_contents", "unit", expected, found)

    normalized_expected = parse_net_contents_ml(expected)
    normalized_found = parse_net_contents_ml(found)
    status = (
        "PASS"
        if normalized_expected is not None
        and normalized_found is not None
        and abs(normalized_expected - normalized_found) <= NET_CONTENTS_ML_TOLERANCE
        else "FAIL"
    )

    return FieldResult(
        field="net_contents",
        match_type="unit",
        expected=expected,
        found=found,
        status=status,
        details=FieldDetails(
            normalized_expected=normalized_expected,
            normalized_found=normalized_found,
            message="Net contents match after ml normalization."
            if status == "PASS"
            else "Net contents are missing, unparseable, or outside tolerance.",
        ),
    )


def compare_government_warning(expected: str, found: str | None) -> FieldResult:
    if found is None:
        return _missing_result("government_warning", "exact", expected, found)

    normalized_expected = collapse_whitespace(expected)
    normalized_found = collapse_whitespace(found)
    status = "PASS" if normalized_expected == normalized_found else "FAIL"

    return FieldResult(
        field="government_warning",
        match_type="exact",
        expected=expected,
        found=found,
        status=status,
        details=FieldDetails(
            normalized_expected=normalized_expected,
            normalized_found=normalized_found,
            message="Government warning matches after whitespace collapse."
            if status == "PASS"
            else "Government warning must match exactly after whitespace collapse, including case and punctuation.",
        ),
    )


def verify_label(application: ApplicationData, extracted: ExtractedLabel) -> VerificationResult:
    start = time.perf_counter()
    comparisons: list[Callable[[], FieldResult]] = [
        lambda: compare_brand_name(application.brand_name, extracted.brand_name),
        lambda: compare_class_type(application.class_type, extracted.class_type),
        lambda: compare_producer(application.producer, extracted.producer),
        lambda: compare_country_of_origin(application.country_of_origin, extracted.country_of_origin),
        lambda: compare_abv(application.abv, extracted.abv),
        lambda: compare_net_contents(application.net_contents, extracted.net_contents),
        lambda: compare_government_warning(
            application.government_warning, extracted.government_warning
        ),
    ]
    fields = [compare() for compare in comparisons]
    overall_verdict = "NEEDS_REVIEW" if any(field.status == "FAIL" for field in fields) else "APPROVED"
    latency_ms = int((time.perf_counter() - start) * 1000)

    return VerificationResult(overall_verdict=overall_verdict, fields=fields, latency_ms=latency_ms)

