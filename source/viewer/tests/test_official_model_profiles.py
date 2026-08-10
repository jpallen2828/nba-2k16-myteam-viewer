from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


VIEWER = Path(__file__).resolve().parents[1]
SOURCE = VIEWER.parent
sys.path.insert(0, str(VIEWER))
sys.path.insert(0, str(SOURCE / "runtime_tools" / "MyTEAM"))

import apply_myteam_roster_live as live  # noqa: E402
import server  # noqa: E402


PROFILE_PATH = VIEWER / "data" / "official_model_profiles.json"
EXPECTED_PLAYER_COUNT = 17
EXPECTED_CARD_COUNT = 26


def load_profiles() -> dict[str, dict]:
    payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    assert payload["format"] == "nba2k16.official-model-profiles/v1"
    return payload["profiles"]


def test_all_captured_profiles_have_verified_exact_bytes_and_hashes():
    profiles = load_profiles()
    assert len(profiles) == EXPECTED_PLAYER_COUNT
    for key, profile in profiles.items():
        assert key == live.norm_player_name(profile["name"])
        sculpt = bytes.fromhex(profile["sculptDnaHex"])
        appearance = bytes.fromhex(profile["appearanceBlockHex"])
        assert len(sculpt) == profile["sculptDnaSize"] == live.SCULPT_DNA_SIZE
        assert len(appearance) == profile["appearanceBlockSize"] == live.APPEARANCE_BLOCK_SIZE
        assert hashlib.sha256(sculpt).hexdigest() == profile["sculptDnaSha256"]
        assert hashlib.sha256(appearance).hexdigest() == profile["appearanceBlockSha256"]
        assert profile["sculptCaptureVerified"] is True
        assert profile["appearanceBlockCaptureVerified"] is True


def test_profiles_contain_no_process_local_pointer_values():
    text = PROFILE_PATH.read_text(encoding="utf-8")
    assert "sculpt_pointer" not in text
    assert "appearance_pointer" not in text
    assert "0x7FF" not in text


def test_every_affected_official_card_receives_its_saved_model_profile():
    profiles = load_profiles()
    affected = [card for card in server.CARDS if live.norm_player_name(card["name"]) in profiles]
    assert len(affected) == EXPECTED_CARD_COUNT
    assert {live.norm_player_name(card["name"]) for card in affected} == set(profiles)
    for card in affected:
        profile = profiles[live.norm_player_name(card["name"])]
        assert card["linkedModelData"] == profile
        assert live.sculpt_dna_bytes(card) == bytes.fromhex(profile["sculptDnaHex"])
        assert live.appearance_block_bytes(card) == bytes.fromhex(profile["appearanceBlockHex"])


def test_saved_hash_mismatch_fails_closed():
    profile = next(iter(load_profiles().values())).copy()
    profile["sculptDnaSha256"] = "0" * 64
    try:
        live.sculpt_dna_bytes({"linkedModelData": profile})
    except ValueError as exc:
        assert "SHA-256" in str(exc)
    else:
        raise AssertionError("A corrupt saved sculpt profile was accepted")
