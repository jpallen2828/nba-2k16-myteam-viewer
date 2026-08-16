"""Build Card Studio's offline player preset and Viewer taxonomy snapshot."""

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.player_data.schema import (
    ATTRIBUTE_GROUPS,
    GAMEPLAY_BADGES,
    GEAR_GROUPS,
    HOT_ZONES,
    PERSONALITY_BADGES,
SIGNATURE_GROUPS,
    TENDENCY_GROUPS,
)


STATIC_THEME_COLLECTIONS = {
    "FIBA": ("FIBA",),
}


ATTRIBUTE_ALIASES = {
    "moving_shot_mid_range": "moving_shot_mid",
    "standing_shot_mid_range": "standing_shot_mid",
    "help_defensive_iq": "help_defense_iq",
}
BADGE_ALIASES = {"fierce_competitor": "fierce_competition"}
SIGNATURE_RANGES = {
    "dribble_posture_iso_spin": (0x0FC, 1),
    "shooting_form": (0x15C, 1),
    "shot_base": (0x15D, 1),
    "post_shimmy_shot": (0x160, 1),
    "post_hook": (0x161, 1),
    "post_hop_shot": (0x163, 1),
    "layup_package": (0x1DF, 1),
    "spin_jumper_post_protect": (0x1E0, 1),
    "dribble_pullup": (0x1E1, 1),
    "post_fade": (0x1E2, 1),
    "dunk_packages_5_12": (0x2B4, 7),
    "free_throw": (0x2D4, 1),
    "iso_hesitation": (0x2D5, 1),
    "signature_sizeup": (0x2D8, 1),
    "dunk_packages_13_15": (0x2D9, 3),
    "dunk_packages_2_4_iso_cross": (0x2E5, 6),
    "iso_sizeup_escape_insideout": (0x2EC, 2),
    "iso_crossover": (0x2EE, 1),
    "hop_jumper": (0x2F0, 1),
}


def name_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def card_key(card: dict) -> str:
    return f"{card.get('id')}/{card.get('slug') or ''}"


def normalize_jersey_number(value: object) -> int | str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if text == "00":
        return "00"
    try:
        return max(0, min(99, int(text)))
    except (TypeError, ValueError):
        return None


def jersey_number_for_card(card: dict, document: dict) -> int | str | None:
    key = card_key(card)
    direct = document.get("cards") or {}
    if key in direct:
        return normalize_jersey_number(direct[key])
    resolved = document.get("resolvedCards") or {}
    if key in resolved:
        return normalize_jersey_number(resolved[key])
    player = name_key(card.get("name"))
    exclusive = document.get("myteamExclusivePlayers") or {}
    if player in exclusive:
        return normalize_jersey_number(exclusive[player])
    year = card.get("year") or "Current"
    franchise = name_key(card.get("franchise"))
    combinations = document.get("playerTeamYears") or {}
    for candidate in (f"{player}|{year}|{franchise}", f"{player}|{year}", f"{player}|{franchise}"):
        if candidate in combinations:
            return normalize_jersey_number(combinations[candidate])
    players = document.get("players") or {}
    return normalize_jersey_number(players.get(player))


def inherited_identity_ids(record: bytes | None) -> dict[str, int]:
    if not record or len(record) < 0x2C2:
        return {}
    return {
        "graphic_id": int.from_bytes(record[0x5C:0x5E], "little"),
        "portrait_ref_a": int.from_bytes(record[0xC4:0xC6], "little"),
        "portrait_ref_b": int.from_bytes(record[0xC6:0xC8], "little"),
        "portrait_ref_c": int.from_bytes(record[0x1EC:0x1EE], "little"),
        "picture_id": int.from_bytes(record[0x2C0:0x2C2], "little"),
    }


def deep_merge(target: dict, incoming: dict) -> dict:
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_merge(target[key], value)
        else:
            target[key] = deepcopy(value)
    return target


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def bundled_custom_cards(viewer_data: Path) -> list[dict]:
    """Load the same valid bundled custom manifests exposed by the Viewer."""
    resolved: dict[str, dict] = {}
    custom_root = viewer_data / "custom-cards"
    if not custom_root.is_dir():
        return []
    for manifest_path in sorted(custom_root.glob("*.json")):
        try:
            manifest = read_json(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, dict) or manifest.get("format") != "nba2k16.custom-card/v1":
            continue
        card = manifest.get("card")
        if not isinstance(card, dict):
            continue
        art_name = str(manifest.get("storedArt") or f"{manifest_path.stem}.png")
        if not (custom_root / art_name).is_file():
            continue
        item = deepcopy(card)
        item["custom"] = True
        resolved[card_key(item)] = item
    return list(resolved.values())


def read_bits(record: bytes | bytearray, offset: int, bit_start: int, bit_length: int) -> int:
    needed = (bit_start + bit_length + 7) // 8
    raw = int.from_bytes(record[offset:offset + needed], "little")
    return (raw >> bit_start) & ((1 << bit_length) - 1)


def decoded_signatures(record: bytes | bytearray) -> dict[str, int]:
    return {
        field["key"]: read_bits(record, field["offset"], field["bit_start"], field["bit_length"])
        for _, fields in SIGNATURE_GROUPS for field in fields
    }


def parse_height(value: object) -> tuple[int, int] | None:
    match = re.search(r"(\d+)\s*['\u2019]\s*(\d+)", str(value or ""))
    return (int(match.group(1)), int(match.group(2))) if match else None


def source_rows(data: dict) -> tuple[dict[str, dict], dict[int, dict]]:
    by_name: dict[str, dict] = {}
    by_slot: dict[int, dict] = {}
    candidates: list[tuple[str, dict]] = []
    candidates.extend((key, value) for key, value in (data.get("players_by_name") or {}).items() if isinstance(value, dict))
    for key, values in (data.get("duplicates_by_name") or {}).items():
        if isinstance(values, list):
            candidates.extend((key, value) for value in values if isinstance(value, dict))
    for raw_key, entry in candidates:
        try:
            bytes.fromhex(str(entry.get("row_hex") or ""))
            slot = int(entry.get("roster_index"))
        except (TypeError, ValueError):
            continue
        by_name.setdefault(name_key(raw_key or entry.get("full_name")), entry)
        by_slot[slot] = entry
    return by_name, by_slot


def apply_signature_profile(record: bytearray, profile: dict | None) -> None:
    if not isinstance(profile, dict):
        return
    for label, (offset, size) in SIGNATURE_RANGES.items():
        raw_hex = str((profile.get("signature_bytes") or {}).get(label) or "")
        try:
            raw = bytes.fromhex(raw_hex)
        except ValueError:
            continue
        if len(raw) == size and offset + size <= len(record):
            record[offset:offset + size] = raw
    release_bits = profile.get("release_timing_bits")
    if release_bits not in (None, "") and len(record) > 0x15F:
        try:
            value = int(str(release_bits), 0) if isinstance(release_bits, str) else int(release_bits)
            record[0x15F] = (record[0x15F] & 0x3F) | (value & 0xC0)
        except (TypeError, ValueError):
            pass


def signature_record(card: dict, by_name: dict[str, dict], by_slot: dict[int, dict], card_overrides: dict, exclusive: dict, signature_overrides: dict[str, bytes], gameplay_profile: dict | None) -> bytes | None:
    entry = None
    explicit_slot = card_overrides.get(card_key(card))
    if explicit_slot is not None:
        entry = by_slot.get(int(explicit_slot))
    if entry is None:
        entry = by_name.get(name_key(card.get("name")))
    named_override = signature_overrides.get(name_key(card.get("name")))
    record = bytearray(named_override) if named_override else bytearray.fromhex(str(entry.get("row_hex") or "")) if entry else bytearray(832)
    profile = exclusive.get(name_key(card.get("name")))
    apply_signature_profile(record, profile)
    apply_signature_profile(record, gameplay_profile)
    return bytes(record) if entry or named_override or isinstance(profile, dict) or isinstance(gameplay_profile, dict) else None


def build_patch(card: dict, signatures: dict[str, int] | None, exclusive_profile: dict | None, gameplay_profile: dict | None, play_override: bool | None, source_record: bytes | None, jersey_number: int | str | None) -> dict:
    identity = {
        "name": str(card.get("name") or ""),
        "year": int(card.get("year") or 2016),
        "overall": int(card.get("overall") or 75),
        "tier": str(card.get("tier") or "Gold"),
        "theme": str(card.get("theme") or ""),
        "collection": str(card.get("collection") or ""),
        "franchise": str(card.get("franchise") or "UNASSIGNED"),
        "primary_position": str(card.get("position") or "PG"),
        "secondary_position": str(card.get("secondaryPosition") or ""),
        "weight": int(round(float(card.get("weight") or 200))),
        "age": int(card.get("age") or 25),
        "from": str(card.get("from") or ""),
        "source_card_id": int(card.get("id") or 0),
        "source_card_slug": str(card.get("slug") or ""),
    }
    identity_ids = inherited_identity_ids(source_record)
    identity["source_identity_ids"] = identity_ids
    identity["face_id"] = int(identity_ids.get("graphic_id") or 0)
    identity["portrait_id"] = int(identity_ids.get("picture_id") or identity_ids.get("portrait_ref_a") or 0)
    if jersey_number is not None:
        identity["jersey_number"] = jersey_number
    height = parse_height(card.get("height"))
    if height:
        identity["height_feet"], identity["height_inches"] = height
    if play_override is not None:
        identity["play_initiator"] = play_override
    if isinstance(exclusive_profile, dict):
        total_inches = exclusive_profile.get("height_inches")
        if total_inches is not None:
            total_inches = int(total_inches)
            identity["height_feet"], identity["height_inches"] = divmod(total_inches, 12)
        for source_key, target_key in (("weight_lbs", "weight"), ("primary_position", "primary_position"), ("secondary_position", "secondary_position"), ("jersey_number", "jersey_number"), ("from", "from")):
            if exclusive_profile.get(source_key) not in (None, ""):
                value = exclusive_profile[source_key]
                identity[target_key] = int(round(value)) if target_key in {"weight", "jersey_number"} else value

    card_attributes = card.get("attributes") or {}
    attributes = {}
    for _, fields in ATTRIBUTE_GROUPS:
        for field in fields:
            source = ATTRIBUTE_ALIASES.get(field, field)
            if source in card_attributes:
                attributes[field] = int(card_attributes[source])

    card_tendencies = dict(card.get("tendencies") or {})
    if isinstance(exclusive_profile, dict):
        card_tendencies.update(exclusive_profile.get("tendencies") or {})
    if isinstance(gameplay_profile, dict):
        card_tendencies.update(gameplay_profile.get("tendencies") or {})
    tendency_fields = {field for _, fields in TENDENCY_GROUPS for field in fields}
    tendencies = {key: int(value) for key, value in card_tendencies.items() if key in tendency_fields}

    raw_badges = card.get("badges") or {}
    personality = {}
    gameplay = {}
    for badge in PERSONALITY_BADGES:
        source = BADGE_ALIASES.get(badge, badge)
        if source in raw_badges:
            personality[badge] = bool(raw_badges[source])
    for badge in GAMEPLAY_BADGES:
        if badge in raw_badges:
            gameplay[badge] = max(0, min(3, int(raw_badges[badge])))

    zones = dict(card.get("hotZones") or {})
    if isinstance(exclusive_profile, dict):
        zones.update(exclusive_profile.get("hot_zones") or {})
    if isinstance(gameplay_profile, dict):
        zones.update(gameplay_profile.get("hot_zones") or gameplay_profile.get("hotZones") or {})
    hot_zones = {key: int(zones[key]) for key in HOT_ZONES if key in zones}
    patch = {
        "identity": identity,
        "attributes": attributes,
        "tendencies": tendencies,
        "badges": {"personality": personality, "gameplay": gameplay},
        "hot_zones": hot_zones,
    }
    if signatures:
        patch["signatures"] = signatures
    return patch


def build_custom_patch(card: dict) -> dict:
    """Translate a Viewer custom card without discarding its captured live data."""
    custom_data = card.get("customPlayerData") or {}
    patch = build_patch(
        card,
        None,
        None,
        None,
        bool(custom_data.get("playInitiator", card.get("playInitiator", False))),
        None,
        card.get("jerseyNumber", custom_data.get("jerseyNumber")),
    )
    attribute_fields = {field for _, fields in ATTRIBUTE_GROUPS for field in fields}
    raw_attributes = card.get("attributes") or {}
    if isinstance(raw_attributes, dict):
        # Viewer custom manifests already use Card Studio's canonical field
        # names, unlike the abbreviated mid-range/help-IQ names in cards.json.
        patch["attributes"] = {
            key: int(value) for key, value in raw_attributes.items() if key in attribute_fields
        }
    identity = patch["identity"]
    identity["face_id"] = int(card.get("faceId", custom_data.get("faceId", 0)) or 0)
    identity["portrait_id"] = int(card.get("portraitId", custom_data.get("portraitId", 0)) or 0)
    inherited = custom_data.get("inheritedIdentityIds")
    identity["source_identity_ids"] = deepcopy(inherited) if isinstance(inherited, dict) else {}
    if card.get("wingspanValue") not in (None, ""):
        identity["wingspan_value"] = int(card["wingspanValue"])

    identity_fields = {
        "dominantHand": "dominant_hand",
        "dominantDunkHand": "dominant_dunk_hand",
        "loyalty": "loyalty",
        "injuryType1": "injury_type_1",
        "injuryDurationDays1": "injury_duration_days_1",
        "injuryType2": "injury_type_2",
        "injuryDurationDays2": "injury_duration_days_2",
        "forceNonStarter": "force_non_starter",
        "playType1": "play_type_1",
        "playType2": "play_type_2",
        "playType3": "play_type_3",
        "playType4": "play_type_4",
    }
    for source, target in identity_fields.items():
        if custom_data.get(source) not in (None, ""):
            identity[target] = custom_data[source]

    signature_fields = {field["key"] for _, fields in SIGNATURE_GROUPS for field in fields}
    raw_signatures = custom_data.get("signatures") or {}
    if isinstance(raw_signatures, dict):
        patch["signatures"] = {
            key: int(value) for key, value in raw_signatures.items() if key in signature_fields
        }

    gear_fields = {key for _, fields in GEAR_GROUPS for key, _ in fields}
    raw_gear = custom_data.get("gear") or {}
    if isinstance(raw_gear, dict):
        patch["gear"] = {key: int(value) for key, value in raw_gear.items() if key in gear_fields}
    return patch


def build(viewer_data: Path) -> dict:
    official_cards = read_json(viewer_data / "cards.json")
    clean = read_json(viewer_data / "clean_roster_sources" / "roster0010_clean_player_rows.json")
    override_doc = read_json(viewer_data / "card_clean_source_overrides.json")
    exclusive_doc = read_json(viewer_data / "myteam_exclusive_source_overrides.json")
    gameplay_doc = read_json(viewer_data / "card_gameplay_overrides.json")
    play_doc = read_json(viewer_data / "play_initiator_overrides.json")
    jersey_doc = read_json(viewer_data / "jersey_number_overrides.json")
    assert isinstance(official_cards, list) and isinstance(clean, dict)
    cards = [*official_cards, *bundled_custom_cards(viewer_data)]
    by_name, by_slot = source_rows(clean)
    card_overrides = (override_doc.get("overrides") or {}) if isinstance(override_doc, dict) else {}
    exclusive = (exclusive_doc.get("players") or {}) if isinstance(exclusive_doc, dict) else {}
    gameplay_cards = (gameplay_doc.get("cards") or {}) if isinstance(gameplay_doc, dict) else {}
    gameplay_profiles = (gameplay_doc.get("profiles") or {}) if isinstance(gameplay_doc, dict) else {}
    signature_overrides = {}
    for path in (viewer_data / "signature-overrides").glob("*.json"):
        data = read_json(path)
        if not isinstance(data, dict):
            continue
        try:
            signature_overrides[name_key(data.get("player"))] = bytes.fromhex(str(data.get("row_hex") or ""))
        except ValueError:
            continue
    play_by_card = (play_doc.get("cards") or {}) if isinstance(play_doc, dict) else {}
    play_by_name = (play_doc.get("players") or {}) if isinstance(play_doc, dict) else {}
    presets = []
    for card in cards:
        if card.get("custom"):
            record = None
            patch = build_custom_patch(card)
        else:
            gameplay_profile = gameplay_profiles.get(gameplay_cards.get(card_key(card)))
            record = signature_record(card, by_name, by_slot, card_overrides, exclusive, signature_overrides, gameplay_profile)
            profile = exclusive.get(name_key(card.get("name")))
            override = play_by_card.get(card_key(card), play_by_name.get(name_key(card.get("name"))))
            patch = build_patch(
                card,
                decoded_signatures(record) if record else None,
                profile,
                gameplay_profile,
                override if isinstance(override, bool) else None,
                record,
                jersey_number_for_card(card, jersey_doc if isinstance(jersey_doc, dict) else {}),
            )
        year = card.get("year") or "Current"
        presets.append({
            "key": card_key(card),
            "label": f"{card.get('name')} — {year} — {card.get('overall')} OVR — {card.get('franchise')}",
            "name": card.get("name"),
            "year": card.get("year"),
            "overall": card.get("overall"),
            "tier": card.get("tier"),
            "theme": card.get("theme") or "",
            "collection": card.get("collection") or "",
            "franchise": card.get("franchise") or "UNASSIGNED",
            "custom": bool(card.get("custom")),
            "hasSignatures": bool(patch.get("signatures")),
            "patch": patch,
        })
    rank = {name: index for index, name in enumerate(("Pink Diamond", "Diamond", "Amethyst", "Gold", "Silver", "Bronze"))}
    presets.sort(key=lambda item: (name_key(item["name"]), rank.get(item["tier"], 99), -int(item["overall"] or 0), -(int(item["year"] or 0))))
    themes = sorted(
        {str(card.get("theme") or "") for card in cards if card.get("theme")}
        | set(STATIC_THEME_COLLECTIONS)
    )
    collections = sorted(
        {str(card.get("collection") or "") for card in cards if card.get("collection")}
        | {collection for values in STATIC_THEME_COLLECTIONS.values() for collection in values}
    )
    theme_collections = {
        theme: sorted({str(card.get("collection") or "") for card in cards if card.get("theme") == theme and card.get("collection")})
        for theme in themes
    }
    for theme, static_collections in STATIC_THEME_COLLECTIONS.items():
        theme_collections[theme] = sorted(set(theme_collections.get(theme, ())) | set(static_collections))
    return {
        "schema": "nba2k16.card-studio-player-presets/v1",
        "source": "NBA 2K16 MyTEAM Viewer official and bundled custom card databases with verified roster source snapshots",
        "count": len(presets),
        "themes": themes,
        "collections": collections,
        "themeCollections": theme_collections,
        "presets": presets,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("viewer_data", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    payload = build(args.viewer_data.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Wrote {payload['count']} presets to {args.output}")


if __name__ == "__main__":
    main()
