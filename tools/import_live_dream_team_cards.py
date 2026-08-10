#!/usr/bin/env python3
"""Capture the user's live Dream Team/Brandon Roy rows as bundled custom cards.

The live player row is authoritative for gameplay data.  Height is deliberately
derived from the linked appearance block, never the often-stale row +0x100
display-height float.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import sys

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "source" / "viewer"
RUNTIME = ROOT / "source" / "runtime_tools"
CARD_STUDIO = ROOT.parent / "NBA 2K16 Card Studio"
ART_ROOT = Path(r"C:\Users\James\Downloads\New PC media files\images\Custom 2k16 cards")
OUTPUT = VIEWER / "data" / "custom-cards"
REPORT = ROOT / "diagnostics" / "live_dream_team_card_import.json"
LOCAL_OUTPUT = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NBA2K16MyTEAMViewer" / "custom-cards"

sys.path[:0] = [str(VIEWER), str(RUNTIME), str(CARD_STUDIO)]

import server  # noqa: E402
import nba2k16_roster_export as roster  # noqa: E402
from MyTEAM import apply_myteam_roster_live as myteam  # noqa: E402
from app.player_data.schema import (  # noqa: E402
    ATTRIBUTE_GROUPS, GAMEPLAY_BADGES, GEAR_GROUPS, HOT_ZONES,
    PERSONALITY_BADGES, SIGNATURE_GROUPS, TENDENCY_GROUPS,
)


SPECS = (
    # Current Cleveland Cavaliers rows.
    {"slot": 48, "team": "Cleveland Cavaliers", "name": "Brandon Roy", "year": 2009, "overall": 87,
     "position": "SG", "height_inches": 78, "art": "Brandon-Roy-2009.png", "franchise": "Portland Trail Blazers",
     "theme": "Historic", "collection": "Trail Blazers Franchise 1", "promotion": "historic_players"},
    {"slot": 49, "team": "Cleveland Cavaliers", "name": "Brandon Roy", "year": 2007, "overall": 82,
     "position": "SG", "height_inches": 78, "art": "Brandon-Roy-2007ROTY.png", "franchise": "Portland Trail Blazers",
     "theme": "Rookie of the Year", "collection": "Rookie of the Year 1", "promotion": "roty"},
    # Current Utah Jazz rows.
    {"slot": 150, "team": "Utah Jazz", "name": "John Stockton", "year": 1992, "overall": 97, "position": "PG", "height_inches": 73,
     "art": "John-Stockton-1992Dream.png", "franchise": "Utah Jazz"},
    {"slot": 151, "team": "Utah Jazz", "name": "Michael Jordan", "year": 1992, "overall": 99, "position": "SG", "height_inches": 78,
     "art": "Michael-Jordan-1992Dream.png", "franchise": "Chicago Bulls"},
    {"slot": 152, "team": "Utah Jazz", "name": "Chris Mullin", "year": 1992, "overall": 97, "position": "SF", "height_inches": 79,
     "art": "Chris-Mullin-1992Dream.png", "franchise": "Golden State Warriors"},
    {"slot": 153, "team": "Utah Jazz", "name": "Charles Barkley", "year": 1992, "overall": 99, "position": "SF", "height_inches": 78,
     "art": "Charles-Barkley-1992Dream.png", "franchise": "Philadelphia 76ers"},
    {"slot": 154, "team": "Utah Jazz", "name": "David Robinson", "year": 1992, "overall": 97, "position": "C", "height_inches": 85,
     "art": "David-Robinson-1992Dream.png", "franchise": "San Antonio Spurs"},
    {"slot": 155, "team": "Utah Jazz", "name": "Clyde Drexler", "year": 1992, "overall": 97, "position": "SG", "height_inches": 79,
     "art": "Clyde-Drexler-1992Dream.png", "franchise": "Portland Trail Blazers"},
    {"slot": 156, "team": "Utah Jazz", "name": "Magic Johnson", "year": 1992, "overall": 92, "position": "PG", "height_inches": 81,
     "art": "Magic-Johnson-1992Dream.png", "franchise": "Los Angeles Lakers"},
    {"slot": 157, "team": "Utah Jazz", "name": "Larry Bird", "year": 1992, "overall": 92, "position": "SF", "height_inches": 81,
     "art": "Larry-Bird-1992Dream.png", "franchise": "Boston Celtics"},
    {"slot": 159, "team": "Utah Jazz", "name": "Patrick Ewing", "year": 1992, "overall": 97, "position": "C", "height_inches": 84,
     "art": "Patrick-Ewing-1992Dream.png", "franchise": "New York Knicks"},
    {"slot": 161, "team": "Utah Jazz", "name": "Karl Malone", "year": 1992, "overall": 97, "position": "PF", "height_inches": 81,
     "art": "Karl-Malone-1992Dream.png", "franchise": "Utah Jazz"},
    {"slot": 162, "team": "Utah Jazz", "name": "Scottie Pippen", "year": 1992, "overall": 96, "position": "SF", "height_inches": 80,
     "art": "Scottie-Pippen-1992Dream.png", "franchise": "Chicago Bulls"},
    {"slot": 164, "team": "Utah Jazz", "name": "Christian Laettner", "year": 1992, "overall": 90, "position": "PF", "height_inches": 83,
     "art": "Christian-Laettner-1992Dream.png", "franchise": "Minnesota Timberwolves"},
)


def schema_audit() -> dict:
    attributes = tuple(name for _, fields in ATTRIBUTE_GROUPS for name in fields)
    tendencies = tuple(name for _, fields in TENDENCY_GROUPS for name in fields)
    signatures = tuple(field["key"] for _, fields in SIGNATURE_GROUPS for field in fields)
    gear = tuple(name for _, fields in GEAR_GROUPS for name, _ in fields)
    badges = (*PERSONALITY_BADGES, *GAMEPLAY_BADGES, "on_court_coach")
    comparisons = {
        "attributes": (set(attributes), set(myteam.ATTRIBUTE_OFFSETS)),
        "tendencies": (set(tendencies), set(myteam.TENDENCY_OFFSETS)),
        "signatures": (set(signatures), set(server.CUSTOM_SIGNATURE_BITS)),
        "gear": (set(gear), set(server.CUSTOM_GEAR_OFFSETS)),
        "hot_zones": (set(HOT_ZONES), set(myteam.HOT_ZONE_FIELDS)),
        "badges": (set(badges), set(myteam.BADGE_FIELDS)),
    }
    mismatches = {
        name: {"card_studio_only": sorted(left - right), "live_decoder_only": sorted(right - left)}
        for name, (left, right) in comparisons.items() if left != right
    }
    if mismatches:
        raise RuntimeError(f"Card Studio/live decoder schema mismatch: {mismatches}")
    return {name: len(left) for name, (left, _right) in comparisons.items()}


def packed(record: bytes, offset: int, start: int, length: int) -> int:
    size = (start + length + 7) // 8
    return (int.from_bytes(record[offset:offset + size], "little") >> start) & ((1 << length) - 1)


def tier(overall: int) -> str:
    if overall >= 99:
        return "Pink Diamond"
    if overall >= 95:
        return "Diamond"
    if overall >= 90:
        return "Amethyst"
    if overall >= 80:
        return "Gold"
    if overall >= 70:
        return "Silver"
    return "Bronze"


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "custom-player"


def card_id(spec: dict) -> int:
    material = "|".join(str(spec[key]) for key in ("name", "year", "overall", "franchise", "position"))
    return 1_000_000_000 + int(hashlib.sha1(material.encode("utf-8")).hexdigest()[:7], 16)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_text_pointer(handle: int, pointer: int) -> str:
    if not pointer:
        return ""
    raw = roster.read_memory(handle, pointer, 128)
    return raw.decode("utf-16-le", errors="ignore").split("\0", 1)[0].strip()


def identity_ids(record: bytes) -> dict[str, int]:
    return {
        field: int.from_bytes(record[offset:offset + 2], "little")
        for field, offset in myteam.IDENTITY_ID_FIELDS.items()
    }


def build_manifest(spec: dict, record: bytes, appearance: bytes, module_base: int, exe_hash: str) -> tuple[dict, dict]:
    actual_name = myteam.record_full_name(record)
    positions = myteam.get_positions(record)
    if actual_name != spec["name"] or positions[0] != spec["position"]:
        raise RuntimeError(f"Slot {spec['slot']} identity mismatch: {actual_name!r} {positions!r}")

    cached = struct.unpack_from("<fff", record, 0x13C)
    displayed = max(25, min(99, math.floor(cached[0] * 100.0 + 0.5)))
    if displayed != spec["overall"]:
        raise RuntimeError(f"Slot {spec['slot']} OVR mismatch: live {displayed}, artwork {spec['overall']}")

    height_cm, wingspan_cm = struct.unpack_from("<ff", appearance, 0)
    derived_height_inches = int(round(height_cm / 2.54))
    if derived_height_inches != spec["height_inches"]:
        raise RuntimeError(
            f"Slot {spec['slot']} linked height mismatch: {height_cm} cm -> {derived_height_inches} in, "
            f"expected {spec['height_inches']} in"
        )
    row_height_inches = struct.unpack_from("<f", record, myteam.HEIGHT_INCHES_OFFSET)[0]

    attributes = {
        field: int(round(float(roster.decode_rating(record[offset]))))
        for field, offset in myteam.ATTRIBUTE_OFFSETS.items()
    }
    tendencies = {field: int(record[offset]) for field, offset in myteam.TENDENCY_OFFSETS.items()}
    badges = {
        field: packed(record, offset, start, length)
        for field, (offset, start, length) in myteam.BADGE_FIELDS.items()
    }
    badges = {field: value for field, value in badges.items() if value}
    signatures = {
        field: packed(record, offset, start, length)
        for field, (offset, start, length) in server.CUSTOM_SIGNATURE_BITS.items()
    }
    gear = {field: int(record[offset]) for field, offset in server.CUSTOM_GEAR_OFFSETS.items()}
    vitals = {
        field: packed(record, offset, start, length)
        for field, (offset, start, length) in server.CUSTOM_VITAL_BITS.items()
    }
    for field in ("injuryDurationDays1", "injuryDurationDays2"):
        vitals[field] = int(vitals[field] // 1440)
    ids = identity_ids(record)
    handedness = server.decode_handedness(record)
    from_pointer = int.from_bytes(record[0x68:0x70], "little")
    origin = read_text_pointer(_LIVE_HANDLE, from_pointer)
    pointer_rva = from_pointer - module_base
    if pointer_rva <= 0:
        raise RuntimeError(f"Slot {spec['slot']} From pointer is not executable-relative")

    art_path = ART_ROOT / spec["art"]
    if not art_path.is_file():
        raise FileNotFoundError(art_path)
    with Image.open(art_path) as image:
        if image.size != (325, 455) or image.format != "PNG":
            raise RuntimeError(f"Unexpected artwork format for {art_path}: {image.format} {image.size}")

    current_year = 2015
    age = max(0, current_year - int(vitals["birthYear"]))
    identifier = card_id(spec)
    card_slug = f"custom-{slug(spec['name'])}-{spec['year']}-{identifier}"
    olympic = spec["year"] == 1992
    theme = "USA Olympics" if olympic else spec["theme"]
    collection = "USA Olympics" if olympic else spec["collection"]
    promotion = "usa_olympic" if olympic else spec["promotion"]
    secondary = "" if positions[1] in {None, "N/A"} else str(positions[1])
    jersey = myteam.get_jersey_number(record)
    custom = {
        **vitals,
        "playInitiator": bool(myteam.get_play_initiator(record)),
        "jerseyNumber": jersey,
        "faceId": ids["graphic_id"],
        "portraitId": ids["picture_id"],
        "inheritedIdentityIds": ids,
        "dominantHand": handedness["dominant_hand"],
        "dominantDunkHand": handedness["dominant_dunk_hand"],
        "signatures": signatures,
        "gear": gear,
        "gearCaptureVerified": True,
        "sourceExecutableSha256": exe_hash.lower(),
        "fromPointerRva": f"0x{pointer_rva:X}",
        "appearance": {"height_cm": float(height_cm), "wingspan_cm": float(wingspan_cm)},
        "sourceRowSha256": sha256(record),
        "sourceAppearanceSha256": sha256(appearance),
        "sourceLiveSlot": spec["slot"],
        "sourceLiveTeam": spec["team"],
    }
    gameplay_values = [value for field, value in badges.items() if field in GAMEPLAY_BADGES]
    card = {
        "id": identifier,
        "slug": card_slug,
        "custom": True,
        "name": spec["name"],
        "overall": spec["overall"],
        "tier": tier(spec["overall"]),
        "year": spec["year"],
        "franchise": spec["franchise"],
        "collection": collection,
        "theme": theme,
        "promotionLogoId": promotion,
        "position": positions[0],
        "secondaryPosition": secondary,
        "height": f"{derived_height_inches // 12}'{derived_height_inches % 12}\"",
        "heightInches": derived_height_inches,
        "wingspanValue": 50,
        "weight": int(round(struct.unpack_from("<f", record, 0x4C)[0])),
        "age": age,
        "from": origin,
        "jerseyNumber": jersey,
        "faceId": ids["graphic_id"],
        "portraitId": ids["picture_id"],
        "playInitiator": bool(myteam.get_play_initiator(record)),
        "parentCardId": 0,
        "parentCardSlug": "",
        "attributes": attributes,
        "tendencies": tendencies,
        "hotZones": myteam.get_hot_zones(record),
        "badges": badges,
        "badgeCounts": {
            "bronze": sum(value == 1 for value in gameplay_values),
            "silver": sum(value == 2 for value in gameplay_values),
            "gold": sum(value == 3 for value in gameplay_values),
        },
        "customPlayerData": custom,
    }
    manifest = {
        "format": server.CUSTOM_CARD_FORMAT,
        "version": 1,
        "imported": datetime.now().astimezone().isoformat(),
        "sourceName": art_path.name,
        "storedArt": f"{identifier}-{card_slug}.png",
        "card": card,
    }
    audit = {
        "slot": spec["slot"], "team": spec["team"], "name": spec["name"],
        "cachedOverall": cached[0], "displayedOverall": displayed,
        "rowHeightInches": row_height_inches,
        "linkedHeightCm": height_cm, "linkedHeightInches": derived_height_inches,
        "linkedWingspanCm": wingspan_cm, "heightSource": "linked appearance block +0x00",
        "origin": origin, "rowSha256": sha256(record), "appearanceSha256": sha256(appearance),
        "artSha256": sha256(art_path.read_bytes()), "manifestStem": f"{identifier}-{card_slug}",
        "fieldCounts": {
            "attributes": len(attributes), "tendencies": len(tendencies), "signatures": len(signatures),
            "gear": len(gear), "hotZones": len(card["hotZones"]), "badgesNonZero": len(badges),
        },
    }
    return manifest, audit


_LIVE_HANDLE = 0


def main() -> int:
    global _LIVE_HANDLE
    schema_counts = schema_audit()
    pid, array_base, exe_path, handle = myteam.open_game(write=False)
    _LIVE_HANDLE = handle
    module_base = array_base - roster.PLAYER_ARRAY_RVA
    exe_hash = roster.sha256(exe_path)
    records: list[dict] = []
    outputs: list[tuple[Path, Path]] = []
    OUTPUT.mkdir(parents=True, exist_ok=True)
    LOCAL_OUTPUT.mkdir(parents=True, exist_ok=True)
    try:
        for spec in SPECS:
            address = array_base + spec["slot"] * roster.PLAYER_STRIDE
            record = roster.read_memory(handle, address, roster.PLAYER_STRIDE)
            pointer = int.from_bytes(
                record[myteam.APPEARANCE_POINTER_OFFSET:myteam.APPEARANCE_POINTER_OFFSET + 8], "little"
            )
            if not pointer:
                raise RuntimeError(f"Slot {spec['slot']} has no linked appearance pointer")
            appearance = roster.read_memory(handle, pointer, myteam.APPEARANCE_BLOCK_SIZE)
            manifest, audit = build_manifest(spec, record, appearance, module_base, exe_hash)
            # Confirm the live inputs did not move while this card was decoded.
            if roster.read_memory(handle, address, roster.PLAYER_STRIDE) != record:
                raise RuntimeError(f"Slot {spec['slot']} changed during capture")
            if roster.read_memory(handle, pointer, myteam.APPEARANCE_BLOCK_SIZE) != appearance:
                raise RuntimeError(f"Slot {spec['slot']} appearance changed during capture")
            stem = f"{manifest['card']['id']}-{manifest['card']['slug']}"
            manifest_path = OUTPUT / f"{stem}.json"
            art_path = OUTPUT / f"{stem}.png"
            temporary = manifest_path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            temporary.replace(manifest_path)
            shutil.copy2(ART_ROOT / spec["art"], art_path)
            shutil.copy2(manifest_path, LOCAL_OUTPUT / manifest_path.name)
            shutil.copy2(art_path, LOCAL_OUTPUT / art_path.name)
            records.append(audit)
            outputs.append((manifest_path, art_path))
    finally:
        roster._close(handle)
        _LIVE_HANDLE = 0

    # Verify through the Viewer's authoritative loader, including artwork resolution.
    loaded = server.load_custom_cards(include_disabled=True, include_hidden=True)
    loaded_keys = {(int(card["id"]), str(card["slug"])) for card in loaded}
    expected_keys = {
        (int(json.loads(path.read_text(encoding="utf-8"))["card"]["id"]),
         str(json.loads(path.read_text(encoding="utf-8"))["card"]["slug"]))
        for path, _art in outputs
    }
    missing = sorted(expected_keys - loaded_keys)
    if missing:
        raise RuntimeError(f"Viewer loader did not resolve imported cards: {missing}")

    payload = {
        "schema": "nba2k16.live-dream-team-card-import/v1",
        "capturedAt": datetime.now().astimezone().isoformat(),
        "mode": "read-only live roster capture",
        "processId": pid,
        "gameExecutable": str(exe_path),
        "gameExecutableSha256": exe_hash,
        "schemaFieldCounts": schema_counts,
        "cardCount": len(records),
        "viewerLoaderVerified": True,
        "bundledOutput": str(OUTPUT.resolve()),
        "localOutput": str(LOCAL_OUTPUT.resolve()),
        "cards": records,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
