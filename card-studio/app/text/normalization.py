"""Input normalization shared by the UI, project loader, and renderer."""

from __future__ import annotations

import re

NAME_ALLOWED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .-'")
POSITION_ALLOWED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def normalize_name(value: object, maximum_length: int = 40) -> str:
    text = " ".join(str(value or "").upper().split())
    text = "".join(character for character in text if character in NAME_ALLOWED)
    return text[:maximum_length].rstrip()


def normalize_position(value: object, maximum_length: int = 2) -> str:
    text = "".join(character for character in str(value or "").upper() if character in POSITION_ALLOWED)
    return text[:maximum_length]


def normalize_overall(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return ""
    return str(max(0, min(99, int(digits))))
