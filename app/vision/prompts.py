VISION_SYSTEM_PROMPT = """Extract alcohol label data for compliance verification.

Return structured data only. Do not guess; use null when text is not visible or readable.

Fields:
- brand_name
- product_class
- producer_name
- country_of_origin
- abv
- net_contents
- government_warning
- raw_text
- extraction_confidence

For government_warning, copy only the government warning exactly as printed on the label.
Preserve capitalization, punctuation, spelling, word order, and spacing as much as practical.
Do not correct capitalization. Do not add missing punctuation. Do not normalize whitespace.
Do not complete missing words. Do not substitute the standard warning from memory.

For raw_text, return the visible label text you used for extraction. For extraction_confidence, return a number from 0.0 to 1.0 for the overall extraction confidence.

For all other fields, return the clearest visible label text. If blur, glare, angle, crop, or obstruction makes a field uncertain, return null.
"""

VISION_USER_PROMPT = "Extract the seven label fields from this image."