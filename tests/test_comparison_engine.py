from app.comparison.engine import (
    GOVERNMENT_WARNING,
    compare_abv,
    compare_brand_name,
    compare_country_of_origin,
    compare_government_warning,
    compare_net_contents,
    verify_label,
)
from app.comparison.models import ApplicationData, ExtractedLabel
from app.comparison.normalizers import parse_abv_percent


def test_brand_case_only_difference_passes() -> None:
    result = compare_brand_name("ACME WINE", "acme wine")

    assert result.status == "PASS"
    assert result.details.score is not None
    assert result.details.score >= 90


def test_short_brand_does_not_match_longer_superset() -> None:
    result = compare_brand_name("ACME", "ACME RESERVE SPECIAL EDITION")

    assert result.status == "FAIL"


def test_parse_abv_percent_converts_proof_to_percent() -> None:
    assert parse_abv_percent("90 Proof") == 45.0


def test_abv_ignores_proof_text_when_matching_percent() -> None:
    result = compare_abv("45%", "45% Alc./Vol. (90 Proof)")

    assert result.status == "PASS"
    assert result.details.normalized_expected == 45.0
    assert result.details.normalized_found == 45.0


def test_abv_outside_tolerance_fails() -> None:
    result = compare_abv("13.5%", "14.0%")

    assert result.status == "FAIL"


def test_net_contents_compact_unit_passes() -> None:
    result = compare_net_contents("750 mL", "750ml")

    assert result.status == "PASS"
    assert result.details.normalized_expected == 750.0
    assert result.details.normalized_found == 750.0


def test_net_contents_liters_and_centiliters_normalize_to_ml() -> None:
    liters = compare_net_contents("0.75 L", "750 ml")
    centiliters = compare_net_contents("75 cl", "750 ml")

    assert liters.status == "PASS"
    assert centiliters.status == "PASS"


def test_country_usa_synonym_passes() -> None:
    result = compare_country_of_origin("USA", "United States")

    assert result.status == "PASS"
    assert result.details.normalized_expected == "united states"
    assert result.details.normalized_found == "united states"


def test_net_contents_fl_oz_normalizes_to_ml() -> None:
    result = compare_net_contents("750 mL", "25.36 fl oz")

    assert result.status == "PASS"


def test_country_prefix_and_expanded_synonym_passes() -> None:
    result = compare_country_of_origin("Germany", "Product of Deutschland")

    assert result.status == "PASS"
    assert result.details.normalized_expected == "germany"
    assert result.details.normalized_found == "germany"


def test_government_warning_whitespace_collapse_passes() -> None:
    ocr_wrapped = GOVERNMENT_WARNING.replace("According to", "According\n   to")

    result = compare_government_warning(GOVERNMENT_WARNING, ocr_wrapped)

    assert result.status == "PASS"


def test_country_different_country_fails() -> None:
    result = compare_country_of_origin("USA", "France")

    assert result.status == "FAIL"


def test_government_warning_title_case_fails() -> None:
    title_case_warning = GOVERNMENT_WARNING.replace(
        "GOVERNMENT WARNING:", "Government Warning:"
    )

    result = compare_government_warning(GOVERNMENT_WARNING, title_case_warning)

    assert result.status == "FAIL"


def test_government_warning_missing_colon_fails() -> None:
    missing_colon = GOVERNMENT_WARNING.replace("GOVERNMENT WARNING:", "GOVERNMENT WARNING")

    result = compare_government_warning(GOVERNMENT_WARNING, missing_colon)

    assert result.status == "FAIL"


def test_government_warning_exact_all_caps_passes() -> None:
    result = compare_government_warning(GOVERNMENT_WARNING, GOVERNMENT_WARNING)

    assert result.status == "PASS"


def test_government_warning_misread_preserves_extracted_text() -> None:
    misread = GOVERNMENT_WARNING.replace("ability", "abiiity")

    result = compare_government_warning(GOVERNMENT_WARNING, misread)

    assert result.status == "FAIL"
    assert result.found == misread


def test_missing_extracted_field_fails() -> None:
    result = compare_brand_name("Acme Wine", None)

    assert result.status == "FAIL"


def test_verify_label_passes_when_all_fields_pass() -> None:
    application = ApplicationData(
        brand_name="ACME WINE",
        class_type="Cabernet Sauvignon",
        producer="Acme Winery LLC",
        country_of_origin="USA",
        abv="45%",
        net_contents="750 mL",
        government_warning=GOVERNMENT_WARNING,
    )
    extracted = ExtractedLabel(
        brand_name="acme wine",
        class_type="cabernet sauvignon",
        producer="Acme Winery",
        country_of_origin="United States",
        abv="45% Alc./Vol. (90 Proof)",
        net_contents="750ml",
        government_warning=GOVERNMENT_WARNING,
    )

    result = verify_label(application, extracted)

    assert result.overall_verdict == "APPROVED"
    assert all(field.status == "PASS" for field in result.fields)


def test_verify_label_needs_review_when_any_field_fails() -> None:
    application = ApplicationData(
        brand_name="ACME WINE",
        class_type="Cabernet Sauvignon",
        producer="Acme Winery LLC",
        country_of_origin="USA",
        abv="45%",
        net_contents="750 mL",
        government_warning=GOVERNMENT_WARNING,
    )
    extracted = ExtractedLabel(
        brand_name="Different Brand",
        class_type="cabernet sauvignon",
        producer="Acme Winery",
        country_of_origin="United States",
        abv="45% Alc./Vol. (90 Proof)",
        net_contents="750ml",
        government_warning=GOVERNMENT_WARNING,
    )

    result = verify_label(application, extracted)

    assert result.overall_verdict == "NEEDS_REVIEW"
    assert any(field.field == "brand_name" and field.status == "FAIL" for field in result.fields)

