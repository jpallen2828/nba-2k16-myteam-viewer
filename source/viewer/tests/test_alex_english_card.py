from __future__ import annotations

import json
from pathlib import Path


CARD = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "custom-cards"
    / "1129164473-custom-alex-english-1983-1129164473.json"
)


def test_alex_english_uses_denver_jersey_number_two():
    card = json.loads(CARD.read_text(encoding="utf-8-sig"))["card"]
    assert card["name"] == "Alex English"
    assert card["jerseyNumber"] == 2
    assert card["customPlayerData"]["jerseyNumber"] == 2
