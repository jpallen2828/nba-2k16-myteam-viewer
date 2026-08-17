from __future__ import annotations

import json
from pathlib import Path
import struct
import sys


VIEWER = Path(__file__).resolve().parents[1]
RUNTIME = VIEWER.parents[1] / "runtime_tools"
sys.path[:0] = [str(VIEWER), str(RUNTIME)]

import server  # noqa: E402
import nba2k16_roster_export as roster  # noqa: E402
from MyTEAM import apply_myteam_roster_live as myteam  # noqa: E402


CUSTOM_ROOT = VIEWER / "data" / "custom-cards"
BATCH = "ray-custom-cards-20260817"
NO_GEAR_FALLBACKS = {
    "JERROD MUSTAF 1993.2k16custom",
    "MEHMET OKUR 2004.2k16custom",
    "PEJA STOJAKOVIC FIBA.2k16custom",
    "RICHARD DUMAS 1993.2k16custom",
}
CLEAN_ROSTER_CAPTURES = {
    "ANDREI KIRILENKO FIBA.2k16custom",
    "DRAZEN PETROVIC FIBA.2k16custom",
    "NIKOLA MIROTIC FIBA.2k16custom",
    "PATRICK MILLS FIBA.2k16custom",
    "SARUNAS MARCIULIONIS FIBA.2k16custom",
    "TONI KUKOC FIBA.2k16custom",
}


def batch_manifests() -> list[dict]:
    manifests = []
    for path in CUSTOM_ROOT.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if payload.get("importBatch") == BATCH:
            manifests.append(payload)
    return manifests


def test_ray_batch_is_complete_and_verified_gear_has_a_traced_roster_source():
    manifests = batch_manifests()
    assert len(manifests) == 60
    by_source = {manifest["sourceName"]: manifest for manifest in manifests}
    assert set(by_source) >= NO_GEAR_FALLBACKS | CLEAN_ROSTER_CAPTURES
    verified = []
    for source_name, manifest in by_source.items():
        card = manifest["card"]
        art = CUSTOM_ROOT / manifest["storedArt"]
        assert art.is_file()
        custom = card["customPlayerData"]
        assert custom["gearCaptureVerified"] is True
        if source_name in NO_GEAR_FALLBACKS:
            assert custom["gearCaptureScope"].startswith("explicit no-gear fallback")
            assert custom["gearCaptureMode"] == "explicit-no-gear"
            assert set(custom["gear"]) == set(server.CUSTOM_GEAR_OFFSETS)
            assert set(custom["gear"].values()) == {0}
        elif source_name in CLEAN_ROSTER_CAPTURES:
            assert custom["gearCaptureScope"].startswith("clean whole-roster same-name source")
            assert custom["sourceLiveTeam"] == "Clean roster whole-array scan"
            assert custom["targetCardOverall"] == card["overall"]
            assert custom["heightCaptureVerified"] is True
        else:
            assert custom["gearCaptureScope"] == "exact normalized name and overall"
            assert custom["sourceLiveTeam"] in {
                "Sacramento Kings", "New York Knicks", "Los Angeles Lakers", "Houston Rockets"
            }
            assert custom["sourceLiveOverall"] == card["overall"]
        assert len(custom["gear"]) == len(server.CUSTOM_GEAR_OFFSETS) == 24
        verified.append(card)
    assert len(verified) == 60


def test_verified_batch_gear_is_written_to_all_mapped_injection_offsets():
    card = next(
        manifest["card"]
        for manifest in batch_manifests()
        if manifest["card"]["customPlayerData"].get("gearCaptureVerified")
    )
    target = bytearray(roster.PLAYER_STRIDE)
    applied = server.apply_custom_player_data(target, card, include_signatures=False, include_gear=True)
    assert len(applied["gear_fields"]) == 24
    for field, offset in server.CUSTOM_GEAR_OFFSETS.items():
        assert target[offset] == card["customPlayerData"]["gear"][field]


def test_no_gear_fallbacks_clear_every_donor_gear_byte():
    manifests = {manifest["sourceName"]: manifest for manifest in batch_manifests()}
    for source_name in NO_GEAR_FALLBACKS:
        card = manifests[source_name]["card"]
        target = bytearray([0xFF]) * roster.PLAYER_STRIDE
        applied = server.apply_custom_player_data(target, card, include_signatures=False, include_gear=True)
        assert len(applied["gear_fields"]) == 24
        assert all(target[offset] == 0 for offset in server.CUSTOM_GEAR_OFFSETS.values())


def test_batch_height_and_taxonomy_corrections_are_hard_coded():
    cards = {manifest["sourceName"]: manifest["card"] for manifest in batch_manifests()}
    nocioni = cards["ANDRES NOCIONI FIBA.2k16custom"]
    assert (nocioni["height"], nocioni["heightInches"]) == ("6'8\"", 80)
    target = bytearray(roster.PLAYER_STRIDE)
    assert server.apply_named_hidden_display_fields(target, nocioni, myteam) == ["display_height_inches@0x100"]
    assert struct.unpack_from("<f", target, myteam.HEIGHT_INCHES_OFFSET)[0] == 80.0

    fiba_cards = [card for card in cards.values() if card.get("promotionLogoId") == "fiba"]
    assert len(fiba_cards) == 20
    assert all((card["theme"], card["collection"]) == ("FIBA", "FIBA") for card in fiba_cards)
    kirilenko = cards["ANDREI KIRILENKO FIBA.2k16custom"]
    assert kirilenko["franchise"] == "Utah Jazz"
    donyell = cards["DONYELL MARSHALL 2007.2k16custom"]
    assert (donyell["franchise"], donyell["collection"]) == (
        "Cleveland Cavaliers", "Cavaliers Franchise 1"
    )
    rasheed = cards["RASHEED WALLACE 2004.2k16custom"]
    assert (rasheed["theme"], rasheed["collection"]) == ("Historic", "Pistons Franchise 1")
