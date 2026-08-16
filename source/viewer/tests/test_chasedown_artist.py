from __future__ import annotations

import json
from pathlib import Path
import sys


SOURCE_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = SOURCE_ROOT / "viewer" / "data"
sys.path.insert(0, str(SOURCE_ROOT / "runtime_tools"))
sys.path.insert(0, str(SOURCE_ROOT / "runtime_tools" / "MyTEAM"))
sys.path.insert(0, str(SOURCE_ROOT / "viewer"))

import apply_myteam_roster_live as live  # noqa: E402
import server  # noqa: E402


def _custom_cards() -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8"))["card"]
        for path in sorted((DATA_ROOT / "custom-cards").glob("*.json"))
    ]


def test_chasedown_artist_uses_verified_live_roster_bits():
    fields = {name: (offset, start, count) for name, offset, start, count in live.roster.BADGES}
    assert fields["chasedown_artist"] == (0x429, 0, 2)

    record = bytearray(live.roster.PLAYER_STRIDE)
    record[0x429] = 0x14
    assert live.set_badge(record, "chasedown_artist", 3)
    assert record[0x429] == 0x17

    stats = live.apply_card_to_record(
        record,
        {"name": "Badge Test", "position": "SF", "badges": {"chasedown_artist": 3}},
        destination_index=0,
    )
    assert record[0x429] & 0x03 == 3
    assert stats["unmatched_badges"] == []


def test_older_local_card_copies_receive_curated_chasedown_level():
    lebron = {
        "id": 1010276239,
        "badges": {"posterizer": 3},
        "badgeCounts": {"bronze": 2, "silver": 4, "gold": 10},
    }
    server.apply_custom_chasedown_artist_level(lebron)
    assert lebron["badges"]["chasedown_artist"] == 3
    assert lebron["badgeCounts"] == {"bronze": 2, "silver": 4, "gold": 11}

    excluded = {
        "id": 1195319080,
        "badges": {"chasedown_artist": 3},
        "badgeCounts": {"bronze": 2, "silver": 4, "gold": 10},
    }
    server.apply_custom_chasedown_artist_level(excluded)
    assert "chasedown_artist" not in excluded["badges"]
    assert excluded["badgeCounts"] == {"bronze": 2, "silver": 4, "gold": 9}


def test_custom_chasedown_artist_assignments():
    cards = _custom_cards()
    pink_diamond_exclusions = {
        "carmelo anthony", "damian lillard", "hedo turkoglu", "james harden",
        "jerry west", "luka doncic", "pete maravich", "stephen curry",
        "tracy mcgrady",
    }
    pink_diamonds = [card for card in cards if card.get("tier") == "Pink Diamond"]
    for card in pink_diamonds:
        name = card["name"].strip().casefold()
        actual = (card.get("badges") or {}).get("chasedown_artist", 0)
        if name == "russell westbrook":
            expected = 1
        elif name == "dirk nowitzki":
            expected = 2
        elif name in pink_diamond_exclusions:
            expected = 0
        else:
            expected = 3
        assert actual == expected, card["name"]

    yao = next(card for card in cards if card["name"].strip().casefold() == "ming yao" and card["tier"] == "Diamond")
    bol = next(card for card in cards if card["name"].strip().casefold() == "manute bol" and card["tier"] == "Gold")
    assert yao["badges"]["chasedown_artist"] == 3
    assert bol["badges"]["chasedown_artist"] == 3


def test_affected_badge_counts_match_badge_data():
    for card in _custom_cards():
        if "chasedown_artist" not in (card.get("badges") or {}):
            continue
        # Personality badges also use 1, so compare against the project's
        # established stored totals only after excluding known personality keys.
        personality = {
            "alpha_dog", "beta_dog", "road_dog", "prime_time", "cool_and_collected",
            "wildcard", "volume_shooter", "closer", "fierce_competition",
            "fierce_competitor", "spark_plug", "swagger", "mind_games", "enforcer",
            "championship_dna", "mentor", "heart_and_soul", "floor_general",
            "defensive_anchor", "hardened", "gym_rat", "reserved", "friendly",
            "low_ego", "all_time_great", "high_work_ethic", "legendary_work_ethic",
            "keep_it_real", "pat_my_back", "expressive", "unpredictable", "laid_back",
            "on_court_coach",
        }
        gameplay = [value for key, value in card["badges"].items() if key not in personality and value in (1, 2, 3)]
        assert card["badgeCounts"] == {
            "bronze": gameplay.count(1),
            "silver": gameplay.count(2),
            "gold": gameplay.count(3),
        }
