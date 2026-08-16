from __future__ import annotations

import base64
import io
import json
import os
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import importlib.util
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVER_PATH = PROJECT_ROOT / "server.py"
spec = importlib.util.spec_from_file_location("viewer_server", SERVER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("Unable to load viewer server module.")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
sys.modules["viewer_server"] = server


ONE_BY_ONE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2A/7YAAAAASUVORK5CYII="
)


def _make_zip(manifest: dict, manifest_name: str = "manifest.json", art_name: str = "card.png") -> bytes:
    with io.BytesIO() as stream:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as package:
            package.writestr(manifest_name, json.dumps(manifest))
            package.writestr(art_name, ONE_BY_ONE_PNG)
        return stream.getvalue()


def _usa_olympics_manifest(card_overrides: dict | None = None) -> dict:
    card = {
        "id": 123456789,
        "slug": "usa-olympics-card",
        "name": "Alex Example",
        "overall": 88,
        "tier": "Gold",
        "year": 2026,
        "franchise": "USA",
        "position": "C",
        "attributes": {"strength": 95},
        "tendencies": {"close_shot": 50},
        "badges": {"alpha_dog": 1},
        "theme": "USA Olympics",
        "collection": "USA Olympics",
        "jerseyNumber": 21,
        "customPlayerData": {
            "gear": {"sock_length_home": 12, "shoe_packed_1": 21},
            "signatures": {"release_timing": 0, "shooting_form": 82, "shot_base": 80},
            "appearance": {"height_cm": 200.7, "wingspan_cm": 209.1},
            "dominantHand": "Right",
            "dominantDunkHand": "Right",
        },
        "height": "6'7\"",
        "heightInches": 79,
        "weight": 210,
        "age": 31,
        "from": "New York",
        "plays": "Outside shooting",
    }
    if card_overrides:
        card.update(card_overrides)
    return {
        "format": server.CUSTOM_CARD_FORMAT,
        "version": 1,
        "card": card,
    }


def _import_manifest(manifest):
    return server.import_custom_card_package(_make_zip(manifest), original_name="test.2k16custom")


def _load_imported_card(card):
    cards = server.load_custom_cards(include_disabled=True, include_hidden=True)
    return next((item for item in cards if item["id"] == card["id"] and item["slug"] == card["slug"]), None)


class CustomImportTests(unittest.TestCase):

    def setUp(self):
        self._tempdir = TemporaryDirectory()
        self._previous_localappdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = str(Path(self._tempdir.name))
        self.addCleanup(self._tempdir.cleanup)
        self.addCleanup(self._restore_localappdata)

    def _restore_localappdata(self):
        if self._previous_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._previous_localappdata

    def test_valid_import_saves_manifest_and_png(self):
        card = _import_manifest(_usa_olympics_manifest())
        self.assertEqual(card["theme"], "USA Olympics")
        self.assertEqual(card["collection"], "USA Olympics")
        self.assertEqual(card["customPlayerData"]["gear"], {"sock_length_home": 12, "shoe_packed_1": 21})
        self.assertEqual(card["customPlayerData"]["signatures"], {"release_timing": 0, "shooting_form": 82, "shot_base": 80})
        self.assertEqual(card["customPlayerData"]["appearance"], {"height_cm": 200.7, "wingspan_cm": 209.1})
        manifest_path = server.custom_card_root() / f"{card['id']}-{card['slug']}.json"
        art_path = server.custom_card_root() / f"{card['id']}-{card['slug']}.png"
        saved_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(saved_manifest["card"]["theme"], "USA Olympics")
        self.assertEqual(saved_manifest["card"]["collection"], "USA Olympics")
        self.assertEqual(saved_manifest["card"]["badges"], {"alpha_dog": 1})
        self.assertEqual(saved_manifest["card"]["attributes"], {"strength": 95})
        self.assertEqual(saved_manifest["card"]["tendencies"], {"close_shot": 50})
        self.assertTrue(art_path.is_file())
        self.assertGreater(art_path.stat().st_size, 0)
        for field, value in card.items():
            if field == "customArtUrl":
                continue
            self.assertEqual(saved_manifest["card"][field], value)

    def test_rejects_missing_manifest(self):
        with self.assertRaisesRegex(ValueError, "Package must contain manifest.json and card.png"):
            server.import_custom_card_package(_make_zip(_usa_olympics_manifest(), manifest_name="not-manifest.json"))

    def test_rejects_missing_card_png(self):
        with self.assertRaisesRegex(ValueError, "Package must contain manifest.json and card.png"):
            server.import_custom_card_package(_make_zip(_usa_olympics_manifest(), art_name="not-card.png"))

    def test_rejects_malformed_zip(self):
        with self.assertRaisesRegex(ValueError, "Could not read custom card package"):
            server.import_custom_card_package(b"not-a-zip", original_name="bad.2k16custom")

    def test_rejects_unsafe_zip_member_names(self):
        with self.assertRaisesRegex(ValueError, "Unsafe ZIP entry"):
            server.import_custom_card_package(_make_zip(_usa_olympics_manifest(), manifest_name="../manifest.json"))

    def test_duplicate_id_slug_replaces_existing(self):
        first_card = _import_manifest(_usa_olympics_manifest({"year": 2024, "name": "First Name"}))
        second_card = _import_manifest(_usa_olympics_manifest({"year": 2025, "name": "Second Name"}))
        manifest_path = server.custom_card_root() / f"{second_card['id']}-{second_card['slug']}.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["card"]["name"], "Second Name")
        self.assertEqual(manifest["card"]["year"], 2025)

    def test_usa_olympics_collection_theme_persisted_after_reload(self):
        card = _import_manifest(_usa_olympics_manifest())
        loaded = _load_imported_card(card)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["theme"], "USA Olympics")
        self.assertEqual(loaded["collection"], "USA Olympics")

    def test_fiba_promotion_metadata_uses_matching_theme_and_collection(self):
        card = _import_manifest(_usa_olympics_manifest({
            "id": 123456790,
            "slug": "fiba-card",
            "promotionLogoId": "fiba",
            "theme": "Custom",
            "collection": "Custom Cards",
        }))
        self.assertEqual(card["theme"], "FIBA")
        self.assertEqual(card["collection"], "FIBA")
        loaded = _load_imported_card(card)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["theme"], "FIBA")
        self.assertEqual(loaded["collection"], "FIBA")

    def test_duplicate_id_slug_filter_support_for_persistence(self):
        card = _import_manifest(_usa_olympics_manifest())
        self.assertEqual(card["theme"], "USA Olympics")
        self.assertEqual(card["collection"], "USA Olympics")
        self.assertTrue((server.custom_card_root() / f"{card['id']}-{card['slug']}.json").is_file())
        cards = server.load_custom_cards(include_disabled=True, include_hidden=True)
        self.assertTrue(any(item["id"] == card["id"] and item["slug"] == card["slug"] and item["theme"] == "USA Olympics" and item["collection"] == "USA Olympics" for item in cards))

    def test_custom_player_data_survives_import(self):
        _import_manifest(_usa_olympics_manifest({
            "customPlayerData": {
                "signatures": {"release_timing": 5},
                "gear": {"sock_length_home": 77},
                "appearance": {"height_cm": 210.0, "wingspan_cm": 215.0},
            },
        }))
        cards = server.load_custom_cards(include_disabled=True, include_hidden=True)
        found = next(item for item in cards if item["slug"] == "usa-olympics-card" and item["id"] == 123456789)
        self.assertEqual(found["customPlayerData"]["signatures"], {"release_timing": 5})
        self.assertEqual(found["customPlayerData"]["gear"]["sock_length_home"], 77)
        self.assertEqual(found["customPlayerData"]["appearance"], {"height_cm": 210.0, "wingspan_cm": 215.0})

    def test_badges_and_attributes_and_tendencies_survive_import(self):
        _import_manifest(_usa_olympics_manifest({
            "badges": {"alpha_dog": 3, "court_general": 2},
            "attributes": {"strength": 99, "speed": 87},
            "tendencies": {"close_shot": 92, "three_point": 88},
        }))
        cards = server.load_custom_cards(include_disabled=True, include_hidden=True)
        found = next(item for item in cards if item["slug"] == "usa-olympics-card" and item["id"] == 123456789)
        self.assertEqual(found["badges"], {"alpha_dog": 3, "court_general": 2})
        self.assertEqual(found["attributes"]["strength"], 99)
        self.assertEqual(found["attributes"]["speed"], 87)
        self.assertEqual(found["tendencies"]["three_point"], 88)

    def test_rejects_missing_required_identity_fields(self):
        with self.assertRaisesRegex(ValueError, "Custom card is missing required fields"):
            manifest = _usa_olympics_manifest({"slug": ""})
            del manifest["card"]["slug"]
            server.import_custom_card_package(_make_zip(manifest))
        with self.assertRaisesRegex(ValueError, "Custom card is missing required fields"):
            manifest = _usa_olympics_manifest()
            del manifest["card"]["attributes"]
            server.import_custom_card_package(_make_zip(manifest))
        with self.assertRaisesRegex(ValueError, "Custom card is missing required fields"):
            manifest = _usa_olympics_manifest()
            del manifest["card"]["tendencies"]
            server.import_custom_card_package(_make_zip(manifest))
        with self.assertRaisesRegex(ValueError, "Custom card ID and overall must be integers"):
            server.import_custom_card_package(_make_zip(_usa_olympics_manifest({"id": "abc"})))
        with self.assertRaisesRegex(ValueError, "Custom card player name cannot be blank"):
            server.import_custom_card_package(_make_zip(_usa_olympics_manifest({"name": ""})))
        with self.assertRaisesRegex(ValueError, "Custom card ID must be positive"):
            server.import_custom_card_package(_make_zip(_usa_olympics_manifest({"id": 0})))

    def test_existing_custom_cards_still_load(self):
        cards = server.load_custom_cards(include_disabled=True, include_hidden=True)
        self.assertGreater(len(cards), 0)

    def test_load_custom_cards_uses_authoritative_storage(self):
        card = _import_manifest(_usa_olympics_manifest())
        loaded = _load_imported_card(card)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["id"], card["id"])
        self.assertEqual(loaded["slug"], card["slug"])


if __name__ == "__main__":
    unittest.main()
