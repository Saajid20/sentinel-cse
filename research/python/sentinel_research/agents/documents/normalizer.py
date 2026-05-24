from __future__ import annotations

import re


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_whitespace(text: str) -> str:
    normalized_newlines = text.replace("\r\n", "\n").replace("\r", "\n")
    return _WHITESPACE_RE.sub(" ", normalized_newlines).strip()


def build_normalized_text(raw_text: str) -> str:
    return normalize_whitespace(raw_text)
