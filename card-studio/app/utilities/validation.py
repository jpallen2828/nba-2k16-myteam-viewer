"""Shared validation exceptions and helpers."""

from __future__ import annotations

import re

SAFE_TEMPLATE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class CardStudioError(Exception):
    """Base exception for errors safe to present to a user."""


class TemplateValidationError(CardStudioError):
    """Raised when a template cannot be used safely."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("Template validation failed:\n" + "\n".join(f"- {item}" for item in errors))


class ProjectFormatError(CardStudioError):
    """Raised when a project file is malformed or unsupported."""


class ImageLoadError(CardStudioError):
    """Raised when source artwork cannot be decoded."""


class LogoAssetError(CardStudioError):
    """Raised when a packaged team logo is missing or invalid."""


class CardAssetError(CardStudioError):
    """Raised when a packaged background or promotion asset is invalid."""


class ExportError(CardStudioError):
    """Raised when a native PNG cannot be exported or verified."""
