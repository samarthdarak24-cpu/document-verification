"""Semantic classifier for detected document modifications.

Classifies changes into:
- Numerical values (statistics, measurements, percentages, amounts)
- Dates (calendar dates in various formats)
- Registration numbers, IDs, and codes
- Names and entity titles
- Sentences and paragraphs
- Typography and formatting modifications
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

#: Regular expressions for semantic entity detection
NUMBER_REGEX = re.compile(r"^\s*[$€£₹]?\s*-?\d+(?:[,\.]\d+)*%?\s*$")
DATE_REGEX = re.compile(
    r"\b(?:\d{1,4}[-/\.]\d{1,2}[-/\.]\d{1,4}|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{2,4})\b",
    re.IGNORECASE,
)
MONTH_NAME_REGEX = re.compile(
    r"^(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)$",
    re.IGNORECASE,
)
REG_ID_REGEX = re.compile(
    r"\b(?:[A-Z0-9]{2,}[-/][A-Z0-9/-]+|ID[:#\s]*[A-Z0-9]+|REG(?:ISTRATION)?[:#\s]*[A-Z0-9/-]+|ROLL[:#\s]*[A-Z0-9]+)\b",
    re.IGNORECASE,
)
NAME_REGEX = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}$")


def classify_modification(
    removed_text: str,
    added_text: str,
    has_style_change: bool = False,
    is_visual: bool = False,
) -> Tuple[str, str]:
    """Classify a modification into (category, scope).

    Returns:
        (category, scope) where:
        category: "numerical" | "date" | "registration_no" | "name_entity" | "font_only" | "visual_diagram" | "text"
        scope: "word" | "sentence" | "paragraph" | "formatting" | "diagram"
    """
    if is_visual:
        return "visual_diagram", "diagram"

    rem = (removed_text or "").strip()
    add = (added_text or "").strip()
    combined = f"{rem} {add}".strip()

    if not rem and not add and has_style_change:
        return "font_only", "formatting"

    # 1. Registration / ID numbers
    if REG_ID_REGEX.search(rem) or REG_ID_REGEX.search(add):
        return "registration_no", "word"

    # 2. Dates
    if (
        DATE_REGEX.search(rem)
        or DATE_REGEX.search(add)
        or MONTH_NAME_REGEX.match(rem)
        or MONTH_NAME_REGEX.match(add)
    ):
        return "date", "word"

    # 3. Numerical values
    if (NUMBER_REGEX.match(rem) or NUMBER_REGEX.match(add)) or (
        any(char.isdigit() for char in rem) and any(char.isdigit() for char in add) and len(rem.split()) <= 2 and len(add.split()) <= 2
    ):
        return "numerical", "word"

    # 4. Proper names
    if NAME_REGEX.match(rem) or NAME_REGEX.match(add):
        return "name_entity", "word"

    # 5. Scope classification (paragraph vs sentence vs word)
    token_count = max(len(rem.split()), len(add.split()))
    if "\n" in rem or "\n" in add or token_count > 30:
        scope = "paragraph"
    elif token_count > 6 or "." in rem or "." in add:
        scope = "sentence"
    else:
        scope = "word"

    if has_style_change and (rem == add or not rem or not add):
        return "font_only", scope

    return "text", scope
