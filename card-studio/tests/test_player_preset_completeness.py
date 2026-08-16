from __future__ import annotations

import json
from pathlib import Path


STUDIO = Path(__file__).resolve().parents[1]
PUBLIC_VIEWER_DATA = STUDIO.parent / "source" / "viewer" / "data"
STANDALONE_VIEWER_DATA = STUDIO.parent / "NBA 2k16 MyTEAM Viewer Public" / "source" / "viewer" / "data"
VIEWER_DATA = PUBLIC_VIEWER_DATA if PUBLIC_VIEWER_DATA.is_dir() else STANDALONE_VIEWER_DATA
PRESETS = STUDIO / "assets" / "player_database" / "player_presets.json"
ALEX_KEY = "1129164473/custom-alex-english-1983-1129164473"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def viewer_cards() -> dict[str, dict]:
    cards = read_json(VIEWER_DATA / "cards.json")
    result = {f"{card.get('id')}/{card.get('slug') or ''}": card for card in cards}
    custom_root = VIEWER_DATA / "custom-cards"
    for path in sorted(custom_root.glob("*.json")):
        manifest = read_json(path)
        card = manifest.get("card")
        art = custom_root / str(manifest.get("storedArt") or f"{path.stem}.png")
        if manifest.get("format") != "nba2k16.custom-card/v1" or not isinstance(card, dict) or not art.is_file():
            continue
        result[f"{card.get('id')}/{card.get('slug') or ''}"] = card
    return result


def test_preset_ids_exactly_match_viewer_official_and_bundled_custom_cards():
    payload = read_json(PRESETS)
    presets = payload["presets"]
    keys = [preset["key"] for preset in presets]
    assert payload["count"] == len(presets) == len(set(keys))
    assert set(keys) == set(viewer_cards())


def test_alex_english_custom_card_is_fully_available_as_a_preset():
    payload = read_json(PRESETS)
    preset = next(item for item in payload["presets"] if item["key"] == ALEX_KEY)
    patch = preset["patch"]
    identity = patch["identity"]
    assert preset["custom"] is True
    assert (preset["name"], preset["year"], preset["overall"]) == ("Alex English", 1983, 91)
    assert (identity["height_feet"], identity["height_inches"]) == (6, 8)
    assert (identity["face_id"], identity["portrait_id"], identity["jersey_number"]) == (2880, 4485, 2)
    assert len(patch["attributes"]) == 61
    assert len(patch["tendencies"]) == 84
    assert len(patch["signatures"]) == 45
    assert len(patch["gear"]) == 24
    assert len(patch["hot_zones"]) == 14


def test_every_custom_preset_preserves_supported_gameplay_sections():
    source = viewer_cards()
    presets = {item["key"]: item for item in read_json(PRESETS)["presets"]}
    for key, card in source.items():
        if not card.get("custom"):
            continue
        patch = presets[key]["patch"]
        custom_data = card.get("customPlayerData") or {}
        assert patch["attributes"] == card.get("attributes", {})
        assert patch["tendencies"] == card.get("tendencies", {})
        assert patch["hot_zones"] == card.get("hotZones", {})
        if isinstance(custom_data.get("signatures"), dict):
            assert patch["signatures"] == custom_data["signatures"]
        if isinstance(custom_data.get("gear"), dict):
            assert patch["gear"] == custom_data["gear"]
