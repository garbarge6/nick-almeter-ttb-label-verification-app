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


def test_brand_case_only_difference_passes() -> None:
    result = compare_brand_name("ACME WINE", "acme wine")

    assert result.status == "PASS"
    assert result.score is not None
    assert result.score >= 85


def test_abv_ignores_proof_text_when_matching_percent() -> None:
    result = compare_abv("45%", "45% Alc./Vol. (90 Proof)")

    assert result.status == "PASS"
    assert result.normalized_application_value == 45.0
    assert result.normalized_extracted_value == 45.0


def test_abv_outside_tolerance_fails() -> None:
    result = compare_abv("13.5%", "14.0%")

    assert result.status == "FAIL"


def test_net_contents_compact_unit_passes() -> None:
    result = compare_net_contents("750 mL", "750ml")

    assert result.status == "PASS"
    assert result.normalized_application_value == 750.0
    assert result.normalized_extracted_value == 750.0


def test_net_contents_liters_and_centiliters_normalize_to_ml() -> None:
    liters = compare_net_contents("0.75 L", "750 ml")
    centiliters = compare_net_contents("75 cl", "750 ml")

    assert liters.status == "PASS"
    assert centiliters.status == "PASS"


def test_country_usa_synonym_passes() -> None:
    result = compare_country_of_origin("USA", "United States")

    assert result.status == "PASS"
    assert result.normalized_application_value == "united states"
    assert result.normalized_extracted_value == "united states"


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
    assert result.extracted_value == misread


def test_missing_extracted_field_fails() -> None:
    result = compare_brand_name("Acme Wine", None)

    assert result.status == "FAIL"


def test_verify_label_passes_when_all_fields_pass() -> None:
    application = ApplicationData(
        brand_name="ACME WINE",
        product_class="Cabernet Sauvignon",
        producer_name="Acme Winery LLC",
        country_of_origin="USA",
        abv="45%",
        net_contents="750 mL",
        government_warning=GOVERNMENT_WARNING,
    )
    extracted = ExtractedLabel(
        brand_name="acme wine",
        product_class="cabernet sauvignon",
        producer_name="Acme Winery",
        country_of_origin="United States",
        abv="45% Alc./Vol. (90 Proof)",
        net_contents="750ml",
        government_warning=GOVERNMENT_WARNING,
    )

    result = verify_label(application, extracted)

    assert result.verdict == "PASS"
    assert all(field.status == "PASS" for field in result.fields)


def test_verify_label_needs_review_when_any_field_fails() -> None:
    application = ApplicationData(
        brand_name="ACME WINE",
        product_class="Cabernet Sauvignon",
        producer_name="Acme Winery LLC",
        country_of_origin="USA",
        abv="45%",
        net_contents="750 mL",
        government_warning=GOVERNMENT_WARNING,
    )
    extracted = ExtractedLabel(
        brand_name="Different Brand",
        product_class="cabernet sauvignon",
        producer_name="Acme Winery",
        country_of_origin="United States",
        abv="45% Alc./Vol. (90 Proof)",
        net_contents="750ml",
        government_warning=GOVERNMENT_WARNING,
    )

    result = verify_label(application, extracted)

    assert result.verdict == "NEEDS_REVIEW"
    assert any(field.field == "brand_name" and field.status == "FAIL" for field in result.fields)
