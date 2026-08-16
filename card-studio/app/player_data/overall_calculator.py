"""Fast, inspectable NBA 2K16 overall formulas with a Version 1 rollback path."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from app.player_data.schema import OVERALL_ATTRIBUTE_FIELDS, POSITIONS
from app.utilities.paths import project_root


MODEL_SCHEMA = "nba2k16.card-studio-overall-models/v1"
MODEL_SCHEMA_V2 = "nba2k16.card-studio-overall-formula/v2"
DEFAULT_MODEL_PATH = Path("assets/player_database/overall_formula_v2.json")
VERSION1_MODEL_PATH = Path("assets/player_database/overall_models.json")


@dataclass(frozen=True, slots=True)
class OverallEstimate:
    position: str
    overall: int
    raw: float
    validation_mae: float
    validation_rmse: float
    sample_count: int
    model_version: str = "v2"
    winning_category: int | None = None


class OverallCalculator:
    """Evaluate the native-shaped Version 2 formula or the preserved Version 1 model."""

    def __init__(self, payload: dict | None = None, version1_payload: dict | None = None) -> None:
        self._payload = payload if self._valid_v2(payload) else {}
        if self._valid_v1(payload):
            self._version1_payload = payload
        else:
            self._version1_payload = version1_payload if self._valid_v1(version1_payload) else {}

    @classmethod
    def load(cls, path: Path, version1_path: Path | None = None) -> "OverallCalculator":
        payload = cls._read(path)
        version1 = cls._read(version1_path) if version1_path else None
        return cls(payload, version1)

    @classmethod
    def load_default(cls) -> "OverallCalculator":
        root = project_root()
        v2 = cls._read(root / DEFAULT_MODEL_PATH)
        v1 = cls._read(root / VERSION1_MODEL_PATH)
        return cls(v2, v1) if cls._valid_v2(v2) else cls(v1)

    @staticmethod
    def _read(path: Path | None) -> dict | None:
        if path is None:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _valid_v1(payload: object) -> bool:
        if not isinstance(payload, dict) or payload.get("schema") != MODEL_SCHEMA:
            return False
        if tuple(payload.get("attributes") or ()) != OVERALL_ATTRIBUTE_FIELDS:
            return False
        models = payload.get("positions")
        return isinstance(models, dict) and all(position in models for position in POSITIONS)

    @staticmethod
    def _valid_v2(payload: object) -> bool:
        if not isinstance(payload, dict) or payload.get("schema") != MODEL_SCHEMA_V2:
            return False
        if tuple(payload.get("attributes") or ()) != OVERALL_ATTRIBUTE_FIELDS:
            return False
        models = payload.get("positions")
        return (
            isinstance(models, dict)
            and all(position in models for position in POSITIONS)
            and int(payload.get("categoryCount") or 0) == 9
        )

    @property
    def available(self) -> bool:
        return bool(self._payload or self._version1_payload)

    @property
    def model_version(self) -> str:
        return "v2" if self._payload else "v1"

    @property
    def source_card_count(self) -> int:
        if self._payload:
            sources = self._payload.get("sourceDatasets") or {}
            return sum(int(item.get("samples") or 0) for item in sources.values() if isinstance(item, dict))
        return int(self._version1_payload.get("sourceCardCount") or 0)

    @staticmethod
    def _display(raw: float) -> int:
        return max(25, min(99, math.floor(raw + 0.5)))

    def estimate(
        self,
        position: str,
        attributes: dict,
        *,
        height_inches: float | None = None,
        durability: dict | None = None,
    ) -> OverallEstimate:
        if not self._payload:
            return self.estimate_v1(position, attributes)
        position = str(position or "").upper()
        if position not in POSITIONS:
            raise ValueError(f"No NBA 2K16 OVR model is available for position {position!r}")
        model = self._payload["positions"][position]
        values: dict[str, float] = {}
        for field in self._payload["attributes"]:
            try:
                values[field] = max(25.0, min(99.0, float(attributes[field])))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Missing or invalid OVR attribute: {field}") from exc
        durability = durability or attributes
        for field in self._payload.get("durabilityFields") or ():
            try:
                values[field] = max(25.0, min(99.0, float(durability.get(field, 75))))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid OVR durability rating: {field}") from exc
        aggregate_model = self._payload.get("durabilityAggregate") or {}
        aggregate = float(aggregate_model.get("intercept") or 0.0) + sum(
            float(coefficient) * values[field]
            for field, coefficient in (aggregate_model.get("coefficients") or {}).items()
        )
        values["durability_aggregate"] = float(round(aggregate))
        if height_inches is None:
            height_inches = (
                (float(model["heightMinimumCm"]) + float(model["heightMaximumCm"])) / 2.0 / 2.54
            )
        low = float(model["heightMinimumCm"])
        high = float(model["heightMaximumCm"])
        height_rating = (float(height_inches) * 2.54 - low) * 74.0 / (high - low) + 25.0
        values["height_suitability"] = max(25.0, min(99.0, height_rating))
        scores = []
        for category in model["categories"]:
            score = float(category["intercept"])
            score += sum(float(coefficient) * values[field] for field, coefficient in category["coefficients"].items())
            scores.append(max(float(category["minimum"]), min(float(category["maximum"]), score)))
        cached = max(scores)
        raw = cached * 100.0
        validation = ((self._payload.get("initialEvaluation") or {}).get("holdout") or {}).get("byPosition", {}).get(position, {})
        return OverallEstimate(
            position=position,
            overall=self._display(raw),
            raw=raw,
            validation_mae=float(validation.get("cachedOverallMaeRatingPoints") or 0.0),
            validation_rmse=float(validation.get("cachedOverallRmseRatingPoints") or 0.0),
            sample_count=int(validation.get("sampleCount") or 0),
            model_version="v2",
            winning_category=max(range(len(scores)), key=scores.__getitem__),
        )

    def estimate_v1(self, position: str, attributes: dict) -> OverallEstimate:
        position = str(position or "").upper()
        models = self._version1_payload.get("positions")
        if position not in POSITIONS or not isinstance(models, dict):
            raise ValueError(f"No NBA 2K16 Version 1 OVR model is available for position {position!r}")
        model = models[position]
        thresholds = tuple(float(value) for value in model.get("thresholds") or ())
        weights = model.get("weights") or {}
        raw = float(model.get("intercept") or 0.0)
        for field in OVERALL_ATTRIBUTE_FIELDS:
            try:
                value = max(25.0, min(99.0, float(attributes[field])))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Missing or invalid OVR attribute: {field}") from exc
            field_weights = weights.get(field)
            if not isinstance(field_weights, list) or len(field_weights) != len(thresholds):
                raise ValueError(f"Invalid OVR weights for {position} {field}")
            raw += sum(
                max(0.0, value - threshold) / 25.0 * float(weight)
                for threshold, weight in zip(thresholds, field_weights, strict=True)
            )
        raw = max(25.0, min(99.0, raw))
        validation = model.get("validation") or {}
        return OverallEstimate(
            position=position,
            overall=self._display(raw),
            raw=raw,
            validation_mae=float(validation.get("mae") or 0.0),
            validation_rmse=float(validation.get("rmse") or 0.0),
            sample_count=int(model.get("sampleCount") or 0),
            model_version="v1",
        )
