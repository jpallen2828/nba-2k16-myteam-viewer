from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton, QSpinBox

from app.player_data.overall_calculator import OverallCalculator
from app.player_data.schema import OVERALL_ATTRIBUTE_FIELDS, POSITIONS
from app.ui.player_data_editor import PlayerDataEditor


ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "assets" / "player_database" / "overall_models.json"
MODELS_V2 = ROOT / "assets" / "player_database" / "overall_formula_v2.json"
PRESETS = ROOT / "assets" / "player_database" / "player_presets.json"
LIVE_FIXTURES = ROOT / "tests" / "fixtures" / "overall_v2_live_holdout.json"

BOOKER_2021_ATTRIBUTES = {
    "standing_layup": 90, "driving_layup": 89, "post_fadeaway": 70, "post_hook": 37,
    "post_control": 66, "draw_foul": 87, "moving_shot_close": 90, "standing_shot_close": 93,
    "moving_shot_mid_range": 94, "standing_shot_mid_range": 95, "moving_shot_three": 88,
    "standing_shot_three": 88, "free_throw": 89, "ball_control": 89, "passing_vision": 76,
    "passing_iq": 76, "passing_accuracy": 74, "boxout": 51, "offensive_rebound": 45,
    "defensive_rebound": 60, "lateral_quickness": 80, "pass_perception": 79, "block": 53,
    "shot_contest": 81, "steal": 75, "defensive_consistency": 79, "on_ball_defense_iq": 80,
    "pick_and_roll_defense_iq": 78, "help_defensive_iq": 78, "low_post_defense_iq": 47,
    "standing_dunk": 40, "driving_dunk": 70, "contact_dunk": 49, "speed": 85,
    "acceleration": 86, "vertical": 81, "strength": 65, "stamina": 96, "hustle": 82,
    "shot_iq": 94, "hands": 98, "reaction_time": 58, "offensive_consistency": 95,
}


@pytest.fixture(scope="module")
def qt_app():
    application = QApplication.instance() or QApplication(["overall-calculator-tests"])
    yield application


def test_models_match_the_bundled_official_source_and_cover_every_position():
    payload = json.loads(MODELS.read_text(encoding="utf-8"))
    assert payload["sourceSha256"] == hashlib.sha256(PRESETS.read_bytes()).hexdigest()
    assert tuple(payload["attributes"]) == OVERALL_ATTRIBUTE_FIELDS
    assert tuple(payload["positions"]) == POSITIONS
    assert all(
        weight >= 0
        for model in payload["positions"].values()
        for weights in model["weights"].values()
        for weight in weights
    )


def test_position_formulas_are_monotonic_for_every_rating():
    calculator = OverallCalculator.load(MODELS)
    baseline = {field: 75 for field in OVERALL_ATTRIBUTE_FIELDS}
    for position in POSITIONS:
        start = calculator.estimate(position, baseline).raw
        for field in OVERALL_ATTRIBUTE_FIELDS:
            improved = dict(baseline)
            improved[field] = 99
            assert calculator.estimate(position, improved).raw >= start


def test_full_training_fit_stays_within_the_recorded_validation_accuracy():
    calculator = OverallCalculator.load(MODELS)
    payload = json.loads(PRESETS.read_text(encoding="utf-8"))
    errors: dict[str, list[float]] = {position: [] for position in POSITIONS}
    for preset in payload["presets"]:
        patch = preset.get("patch") or {}
        identity = patch.get("identity") or {}
        attributes = patch.get("attributes") or {}
        position = identity.get("primary_position")
        if preset.get("custom") or preset.get("tier") == "Pink Diamond" or str(preset.get("collection") or "").startswith("HIDDEN"):
            continue
        if position not in POSITIONS or not all(field in attributes for field in OVERALL_ATTRIBUTE_FIELDS):
            continue
        estimate = calculator.estimate(position, attributes)
        errors[position].append(abs(estimate.raw - float(preset["overall"])))
    model_payload = json.loads(MODELS.read_text(encoding="utf-8"))
    for position in POSITIONS:
        mean_error = sum(errors[position]) / len(errors[position])
        assert mean_error <= model_payload["positions"][position]["validation"]["mae"]


def test_devin_booker_profile_calculates_as_a_91_overall_shooting_guard():
    calculator = OverallCalculator.load(MODELS)
    estimate = calculator.estimate("SG", BOOKER_2021_ATTRIBUTES)
    assert estimate.overall == 91
    assert estimate.raw == pytest.approx(90.86, abs=0.01)


def test_player_data_editor_shows_decimal_ovr_in_header_and_updates_it_live(qt_app):
    editor = PlayerDataEditor()
    editor.set_player_data({
        "identity": {"primary_position": "SG", "overall": 96},
        "attributes": BOOKER_2021_ATTRIBUTES,
    })
    assert editor._overall_live_display is not None
    assert editor._overall_live_display.text() == "SG OVR 91.30"
    assert editor.findChild(QPushButton, "calculateOverallButton") is None
    overall = editor._controls["identity.overall"]
    assert isinstance(overall, QSpinBox)
    assert overall.value() == 91
    assert editor.player_data()["identity"]["overall"] == 91
    previous = editor._overall_live_display.text()
    editor._controls["attributes.standing_shot_three"].setValue(99)
    assert editor._overall_live_display.text() != previous
    assert "." in editor._overall_live_display.text()
    editor._controls["identity.primary_position"].setCurrentText("PG")
    assert editor._overall_live_display.text().startswith("PG OVR ")


def test_v2_model_loads_and_matches_post_selection_live_holdout_fixtures():
    calculator = OverallCalculator.load(MODELS_V2, MODELS)
    fixtures = json.loads(LIVE_FIXTURES.read_text(encoding="utf-8"))["fixtures"]
    assert calculator.model_version == "v2"
    assert {row["position"] for row in fixtures} == set(POSITIONS)
    for row in fixtures:
        first = calculator.estimate(
            row["position"], row["attributes"],
            height_inches=row["height_inches"], durability=row["durability"],
        )
        second = calculator.estimate(
            row["position"], row["attributes"],
            height_inches=row["height_inches"], durability=row["durability"],
        )
        assert first == second
        assert first.overall == row["displayed_overall"]
        assert first.raw / 100.0 == pytest.approx(row["cached_overall"], abs=0.00012)


def test_v2_height_is_direct_and_irrelevant_extra_fields_are_ignored():
    calculator = OverallCalculator.load(MODELS_V2, MODELS)
    attributes = dict(BOOKER_2021_ATTRIBUTES)
    durability = {field: 75 for field in json.loads(MODELS_V2.read_text())["durabilityFields"]}
    short = calculator.estimate("C", attributes, height_inches=70, durability=durability)
    tall = calculator.estimate("C", attributes, height_inches=86, durability=durability)
    assert tall.raw > short.raw
    attributes["potential"] = 25
    attributes["emotion"] = 99
    repeated = calculator.estimate("C", attributes, height_inches=86, durability=durability)
    assert repeated == tall


def test_missing_or_corrupt_v2_can_fall_back_to_version1(tmp_path):
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    calculator = OverallCalculator.load(corrupt, MODELS)
    assert calculator.model_version == "v1"
    assert calculator.estimate("SG", BOOKER_2021_ATTRIBUTES).overall == 91


def test_version2_live_benchmark_materially_beats_version1():
    calculator = OverallCalculator.load(MODELS_V2, MODELS)
    fixtures = json.loads(LIVE_FIXTURES.read_text(encoding="utf-8"))["fixtures"]
    v1_errors = []
    v2_errors = []
    for row in fixtures:
        actual = row["displayed_overall"]
        v1_errors.append(abs(calculator.estimate_v1(row["position"], row["attributes"]).overall - actual))
        v2 = calculator.estimate(
            row["position"], row["attributes"],
            height_inches=row["height_inches"], durability=row["durability"],
        )
        v2_errors.append(abs(v2.overall - actual))
    assert sum(v2_errors) == 0
    assert sum(v1_errors) > sum(v2_errors)
