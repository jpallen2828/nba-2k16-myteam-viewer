"""Fit reproducible monotonic OVR models from bundled official MyTEAM presets."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import lsq_linear


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.player_data.overall_calculator import MODEL_SCHEMA  # noqa: E402
from app.player_data.schema import OVERALL_ATTRIBUTE_FIELDS, POSITIONS  # noqa: E402


SOURCE = ROOT / "assets" / "player_database" / "player_presets.json"
OUTPUT = ROOT / "assets" / "player_database" / "overall_models.json"

# Chosen independently through grouped five-fold validation. Players, rather
# than individual cards, own folds so alternate versions of the same player
# never leak across the training and validation sides.
FIT_CONFIGS = {
    "PG": {"thresholds": (25, 60, 75, 85, 92), "alpha": 1.0},
    "SG": {"thresholds": (25, 60, 75, 85, 92), "alpha": 3.0},
    "SF": {"thresholds": (25, 40, 55, 70, 85, 95), "alpha": 10.0},
    "PF": {"thresholds": (25, 55, 70, 82, 90, 96), "alpha": 10.0},
    "C": {"thresholds": (25, 55, 70, 82, 90, 96), "alpha": 10.0},
}


def feature_matrix(values: np.ndarray, thresholds: tuple[int, ...]) -> np.ndarray:
    expanded = np.maximum(
        0.0,
        values[:, :, np.newaxis] - np.asarray(thresholds)[np.newaxis, np.newaxis, :],
    ) / 25.0
    return expanded.reshape(len(values), -1)


def fit_monotonic_ridge(features: np.ndarray, labels: np.ndarray, alpha: float) -> np.ndarray:
    design = np.column_stack([np.ones(len(features)), features])
    regularizer = np.zeros((design.shape[1] - 1, design.shape[1]))
    regularizer[:, 1:] = np.eye(design.shape[1] - 1) * np.sqrt(alpha)
    augmented_design = np.vstack([design, regularizer])
    augmented_labels = np.concatenate([labels, np.zeros(len(regularizer))])
    lower = np.concatenate([[-np.inf], np.zeros(design.shape[1] - 1)])
    upper = np.full(design.shape[1], np.inf)
    return lsq_linear(
        augmented_design,
        augmented_labels,
        bounds=(lower, upper),
        tol=1e-11,
        lsmr_tol="auto",
        max_iter=3000,
    ).x


def predict(features: np.ndarray, coefficients: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(features)), features]) @ coefficients


def player_fold(name: str) -> int:
    digest = hashlib.sha256(name.casefold().encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 5


def eligible_rows(payload: dict, position: str) -> list[dict]:
    rows = []
    for preset in payload.get("presets") or ():
        patch = preset.get("patch") or {}
        identity = patch.get("identity") or {}
        attributes = patch.get("attributes") or {}
        collection = str(preset.get("collection") or "")
        if preset.get("custom") or preset.get("tier") == "Pink Diamond" or collection.startswith("HIDDEN"):
            continue
        if identity.get("primary_position") != position:
            continue
        if not all(field in attributes for field in OVERALL_ATTRIBUTE_FIELDS):
            continue
        rows.append(preset)
    return rows


def build_position_model(payload: dict, position: str) -> dict:
    rows = eligible_rows(payload, position)
    values = np.asarray([
        [row["patch"]["attributes"][field] for field in OVERALL_ATTRIBUTE_FIELDS]
        for row in rows
    ], dtype=float)
    labels = np.asarray([row["overall"] for row in rows], dtype=float)
    folds = np.asarray([player_fold(str(row.get("name") or "")) for row in rows])
    config = FIT_CONFIGS[position]
    thresholds = tuple(config["thresholds"])
    features = feature_matrix(values, thresholds)
    validation_predictions = np.zeros(len(rows))
    for fold in range(5):
        training = folds != fold
        coefficients = fit_monotonic_ridge(features[training], labels[training], float(config["alpha"]))
        validation_predictions[~training] = predict(features[~training], coefficients)
    final = fit_monotonic_ridge(features, labels, float(config["alpha"]))
    width = len(thresholds)
    flattened_weights = final[1:]
    weights = {
        field: [round(float(value), 10) for value in flattened_weights[index * width:(index + 1) * width]]
        for index, field in enumerate(OVERALL_ATTRIBUTE_FIELDS)
    }
    errors = validation_predictions - labels
    return {
        "sampleCount": len(rows),
        "thresholds": list(thresholds),
        "ridgeAlpha": config["alpha"],
        "intercept": round(float(final[0]), 10),
        "weights": weights,
        "validation": {
            "method": "grouped-five-fold-by-player",
            "mae": round(float(np.mean(np.abs(errors))), 4),
            "rmse": round(float(np.sqrt(np.mean(errors ** 2))), 4),
            "roundedExactRate": round(float(np.mean(np.rint(validation_predictions) == labels)), 4),
            "highTierMae": round(float(np.mean(np.abs(errors[labels >= 90]))), 4),
        },
    }


def main() -> int:
    source_bytes = SOURCE.read_bytes()
    payload = json.loads(source_bytes.decode("utf-8-sig"))
    result = {
        "schema": MODEL_SCHEMA,
        "version": 1,
        "description": "Monotonic position-specific OVR formulas fitted only from official non-hidden, non-Pink-Diamond NBA 2K16 MyTEAM cards.",
        "source": SOURCE.name,
        "sourceSha256": hashlib.sha256(source_bytes).hexdigest(),
        "sourceCardCount": sum(1 for preset in payload.get("presets") or () if not preset.get("custom")),
        "attributes": list(OVERALL_ATTRIBUTE_FIELDS),
        "formula": "intercept + sum(max(0, rating - threshold) / 25 * nonnegative_weight)",
        "positions": {position: build_position_model(payload, position) for position in POSITIONS},
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)
    for position, model in result["positions"].items():
        validation = model["validation"]
        print(
            f"{position}: n={model['sampleCount']} MAE={validation['mae']:.4f} "
            f"RMSE={validation['rmse']:.4f} exact={validation['roundedExactRate']:.1%}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
