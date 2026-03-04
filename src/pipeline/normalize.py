from __future__ import annotations

import re


WHITESPACE_RE = re.compile(r"\s+")
PRIVATE_USE_RE = re.compile(r"[\uE000-\uF8FF]")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    cleaned = PRIVATE_USE_RE.sub("", value)
    return WHITESPACE_RE.sub(" ", cleaned).strip()


def clean_phone(value: str | None) -> str:
    return clean_text(value)


def clean_web(value: str | None) -> str:
    value = clean_text(value)
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return value


def clean_rating(value: str | None) -> str:
    value = clean_text(value).replace(",", ".")
    if not value:
        return ""
    try:
        # Keep as normalized string for CSV consistency
        return f"{float(value):.1f}".rstrip("0").rstrip(".")
    except ValueError:
        return ""
