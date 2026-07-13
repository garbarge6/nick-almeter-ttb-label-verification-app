import re
from difflib import SequenceMatcher


COUNTRY_SYNONYMS = {
    "us": "united states",
    "u s": "united states",
    "usa": "united states",
    "u s a": "united states",
    "united states": "united states",
    "united states of america": "united states",
    "uk": "united kingdom",
    "u k": "united kingdom",
    "united kingdom": "united kingdom",
    "great britain": "united kingdom",
    "south korea": "south korea",
    "republic of korea": "south korea",
    "czechia": "czech republic",
    "czech republic": "czech republic",
}

LEGAL_SUFFIX_TOKENS = {"llc", "ltd", "inc", "co", "corp", "corporation", "company"}

NET_CONTENT_UNITS = {
    "ml": 1.0,
    "milliliter": 1.0,
    "milliliters": 1.0,
    "l": 1000.0,
    "liter": 1000.0,
    "liters": 1000.0,
    "cl": 10.0,
    "centiliter": 10.0,
    "centiliters": 10.0,
}


def normalize_text(value: str) -> str:
    lowered = value.casefold().strip()
    without_punctuation = re.sub(r"[^\w\s]", " ", lowered)
    tokens = [
        token
        for token in re.sub(r"\s+", " ", without_punctuation).strip().split()
        if token not in LEGAL_SUFFIX_TOKENS
    ]
    return " ".join(tokens)


def token_set_ratio(left: str, right: str) -> float:
    left_tokens = set(normalize_text(left).split())
    right_tokens = set(normalize_text(right).split())

    if not left_tokens or not right_tokens:
        return 0.0

    common = sorted(left_tokens & right_tokens)
    left_diff = sorted(left_tokens - right_tokens)
    right_diff = sorted(right_tokens - left_tokens)

    common_text = " ".join(common)
    left_text = " ".join(common + left_diff)
    right_text = " ".join(common + right_diff)

    ratios = [SequenceMatcher(None, left_text, right_text).ratio()]
    return round(max(ratios) * 100, 2)


def normalize_country(value: str) -> str:
    normalized = normalize_text(value)
    return COUNTRY_SYNONYMS.get(normalized, normalized)


def parse_abv_percent(value: str | float | int) -> float | None:
    if isinstance(value, int | float):
        return float(value)

    match = re.search(r"(\d+(?:\.\d+)?)\s*%", value)
    if match:
        return float(match.group(1))

    match = re.search(r"\b(\d+(?:\.\d+)?)\s*proof\b", value, flags=re.IGNORECASE)
    if match:
        return float(match.group(1)) / 2

    match = re.search(r"\b(\d+(?:\.\d+)?)\b", value)
    if match:
        return float(match.group(1))

    return None


def parse_net_contents_ml(value: str) -> float | None:
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(ml|milliliters?|l|liters?|cl|centiliters?)\b",
        value,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    amount = float(match.group(1))
    unit = match.group(2).casefold()
    multiplier = NET_CONTENT_UNITS.get(unit)

    if multiplier is None:
        return None

    return amount * multiplier
