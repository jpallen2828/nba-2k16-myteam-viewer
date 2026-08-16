"""Portable Card Studio -> MyTEAM Viewer custom-card package export."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from PIL import Image

from app.models.project_model import CardProject
from app.player_data.promotion_taxonomy import apply_promotion_taxonomy
from app.player_data.schema import normalize_player_data
from app.utilities.validation import ExportError


CUSTOM_CARD_EXTENSION = ".2k16custom"
CUSTOM_CARD_FORMAT = "nba2k16.custom-card/v1"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "custom-player"


def _custom_id(data: dict) -> int:
    identity = data["identity"]
    material = "|".join(str(identity.get(key) or "") for key in ("name", "year", "overall", "franchise", "primary_position"))
    # Reserve a stable positive range above official IDs while remaining
    # safely inside a signed 32-bit integer.
    return 1_000_000_000 + int(hashlib.sha1(material.encode("utf-8")).hexdigest()[:7], 16)


def _jersey_number(value) -> int | str:
    text = str(value).strip()
    return "00" if text == "00" else max(0, min(99, int(value or 0)))


def _inherited_identity_ids(identity: dict) -> dict[str, int]:
    fields = ("graphic_id", "portrait_ref_a", "portrait_ref_b", "portrait_ref_c", "picture_id")
    inherited = {
        key: int(value)
        for key in fields
        if (value := (identity.get("source_identity_ids") or {}).get(key)) not in (None, "")
    }
    face_id = int(identity.get("face_id") or 0)
    portrait_id = int(identity.get("portrait_id") or 0)
    if inherited.get("graphic_id") == face_id and inherited.get("picture_id") == portrait_id:
        return inherited
    return {
        "graphic_id": face_id,
        "portrait_ref_a": portrait_id or face_id,
        "portrait_ref_b": portrait_id or face_id,
        "portrait_ref_c": portrait_id or face_id,
        "picture_id": portrait_id or face_id,
    }


def card_payload(player_data: dict, promotion_logo_id: str = "") -> dict:
    data = normalize_player_data(apply_promotion_taxonomy(player_data, promotion_logo_id))
    identity = data["identity"]
    feet = int(identity.get("height_feet") or 6)
    inches = int(identity.get("height_inches") or 0)
    personality = {key: 1 for key, enabled in data["badges"]["personality"].items() if enabled}
    gameplay = {key: int(value) for key, value in data["badges"]["gameplay"].items() if int(value) > 0}
    badge_counts = {
        "bronze": sum(1 for value in gameplay.values() if value == 1),
        "silver": sum(1 for value in gameplay.values() if value == 2),
        "gold": sum(1 for value in gameplay.values() if value == 3),
    }
    if data["badges"].get("on_court_coach"):
        personality["on_court_coach"] = 1
    name = str(identity.get("name") or "Custom Player").strip()
    year = int(identity.get("year") or 2016)
    card_id = _custom_id(data)
    return {
        "id": card_id,
        "slug": f"custom-{_slug(name)}-{year}-{card_id}",
        "custom": True,
        "name": name,
        "overall": int(identity.get("overall") or 75),
        "tier": str(identity.get("tier") or "Gold"),
        "year": year,
        "franchise": str(identity.get("franchise") or "UNASSIGNED"),
        "collection": str(identity.get("collection") or "Custom Cards"),
        "theme": str(identity.get("theme") or "Custom"),
        "promotionLogoId": str(promotion_logo_id or ""),
        "position": str(identity.get("primary_position") or "PG"),
        "secondaryPosition": str(identity.get("secondary_position") or ""),
        "height": f"{feet}'{inches}\"",
        "heightInches": feet * 12 + inches,
        "wingspanValue": 50,
        "weight": int(identity.get("weight") or 200),
        "age": int(identity.get("age") or 25),
        "from": str(identity.get("from") or ""),
        "jerseyNumber": _jersey_number(identity.get("jersey_number")),
        "faceId": int(identity.get("face_id") or 0),
        "portraitId": int(identity.get("portrait_id") or 0),
        "playInitiator": bool(identity.get("play_initiator")),
        "parentCardId": int(identity.get("source_card_id") or 0),
        "parentCardSlug": str(identity.get("source_card_slug") or ""),
        "attributes": {key: int(value) for key, value in data["attributes"].items()},
        "tendencies": {key: int(value) for key, value in data["tendencies"].items()},
        "hotZones": {key: int(value) for key, value in data["hot_zones"].items()},
        "badges": {**personality, **gameplay},
        "badgeCounts": badge_counts,
        "customPlayerData": {
            "signatures": {key: int(value) for key, value in data["signatures"].items()},
            "gear": {key: int(value) for key, value in data["gear"].items()},
            "faceId": int(identity.get("face_id") or 0),
            "portraitId": int(identity.get("portrait_id") or 0),
            "inheritedIdentityIds": _inherited_identity_ids(identity),
            "jerseyNumber": _jersey_number(identity.get("jersey_number")),
            "playInitiator": bool(identity.get("play_initiator")),
            "dominantHand": str(identity.get("dominant_hand") or "Right"),
            "dominantDunkHand": str(identity.get("dominant_dunk_hand") or "Right"),
            "wingspanValue": 50,
            "loyalty": int(identity.get("loyalty") or 0),
            "injuryType1": int(identity.get("injury_type_1") or 0),
            "injuryDurationDays1": int(identity.get("injury_duration_days_1") or 0),
            "injuryType2": int(identity.get("injury_type_2") or 0),
            "injuryDurationDays2": int(identity.get("injury_duration_days_2") or 0),
            "forceNonStarter": int(identity.get("force_non_starter") or 0),
            "playType1": int(identity.get("play_type_1") or 0),
            "playType2": int(identity.get("play_type_2") or 0),
            "playType3": int(identity.get("play_type_3") or 0),
            "playType4": int(identity.get("play_type_4") or 0),
        },
    }


class CustomCardService:
    @staticmethod
    def export(project: CardProject, image: Image.Image, path: Path, expected_size: tuple[int, int]) -> Path:
        try:
            if image.size != expected_size:
                raise ExportError(f"Renderer returned {image.size}; expected {expected_size}.")
            card = card_payload(project.player_data, project.card_assets.promotion_logo_id)
            png = io.BytesIO()
            image.convert("RGBA").save(png, "PNG", optimize=False)
            manifest = {
                "format": CUSTOM_CARD_FORMAT,
                "version": 1,
                "created": datetime.now(timezone.utc).isoformat(),
                "application": "NBA 2K16 Card Studio",
                "image": "card.png",
                "card": card,
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
                archive.writestr("card.png", png.getvalue())
            CustomCardService.verify(path)
            return path
        except ExportError:
            raise
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            raise ExportError(f"Could not export custom card to '{path}': {exc}") from exc

    @staticmethod
    def verify(path: Path) -> None:
        with zipfile.ZipFile(path, "r") as archive:
            if set(("manifest.json", "card.png")) - set(archive.namelist()):
                raise ExportError("Custom-card package is missing manifest.json or card.png.")
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            if manifest.get("format") != CUSTOM_CARD_FORMAT or not isinstance(manifest.get("card"), dict):
                raise ExportError("Custom-card manifest is not a supported NBA 2K16 package.")
            with Image.open(io.BytesIO(archive.read("card.png"))) as image:
                image.verify()
