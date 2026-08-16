"""Validated metadata for a packaged background-removal model."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.background_removal.exceptions import ModelMissingError, ModelValidationError


@dataclass(frozen=True, slots=True)
class ModelMetadata:
    name: str
    version: str
    filename: str
    input_size: tuple[int, int]
    mean: tuple[float, float, float]
    std: tuple[float, float, float]
    output_interpretation: str
    license: str
    source_url: str
    sha256: str

    @classmethod
    def load(cls, path: Path) -> "ModelMetadata":
        if not path.is_file():
            raise ModelMissingError(f"Background-removal metadata is missing: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            size = data["expected_input_size"]
            normalization = data["normalization"]
            result = cls(
                name=str(data["model_name"]),
                version=str(data["version"]),
                filename=str(data["filename"]),
                input_size=(int(size[0]), int(size[1])),
                mean=tuple(float(value) for value in normalization["mean"]),
                std=tuple(float(value) for value in normalization["std"]),
                output_interpretation=str(data["output_interpretation"]),
                license=str(data["license"]),
                source_url=str(data["source_url"]),
                sha256=str(data["sha256"]).lower(),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ModelValidationError(f"Invalid background-removal model metadata: {exc}") from exc
        if len(result.mean) != 3 or len(result.std) != 3 or len(result.sha256) != 64:
            raise ModelValidationError("Background-removal metadata has invalid normalization or SHA-256 values.")
        return result
