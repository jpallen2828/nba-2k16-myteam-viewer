from __future__ import annotations

import json
from pathlib import Path
import unittest

from PIL import Image


VIEWER = Path(__file__).resolve().parents[1]
CUSTOM = VIEWER / "data" / "custom-cards"
EXPECTED = {
    ("Brandon Roy", 2009): (87, 78, "Historic", "Cleveland Cavaliers", 48),
    ("Brandon Roy", 2007): (82, 78, "Rookie of the Year", "Cleveland Cavaliers", 49),
    ("John Stockton", 1992): (97, 73, "USA Olympics", "Utah Jazz", 150),
    ("Michael Jordan", 1992): (99, 78, "USA Olympics", "Utah Jazz", 151),
    ("Chris Mullin", 1992): (97, 79, "USA Olympics", "Utah Jazz", 152),
    ("Charles Barkley", 1992): (99, 78, "USA Olympics", "Utah Jazz", 153),
    ("David Robinson", 1992): (97, 85, "USA Olympics", "Utah Jazz", 154),
    ("Clyde Drexler", 1992): (97, 79, "USA Olympics", "Utah Jazz", 155),
    ("Magic Johnson", 1992): (92, 81, "USA Olympics", "Utah Jazz", 156),
    ("Larry Bird", 1992): (92, 81, "USA Olympics", "Utah Jazz", 157),
    ("Patrick Ewing", 1992): (97, 84, "USA Olympics", "Utah Jazz", 159),
    ("Karl Malone", 1992): (97, 81, "USA Olympics", "Utah Jazz", 161),
    ("Scottie Pippen", 1992): (96, 80, "USA Olympics", "Utah Jazz", 162),
    ("Christian Laettner", 1992): (90, 83, "USA Olympics", "Utah Jazz", 164),
}


class LiveDreamTeamCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = {}
        for path in CUSTOM.glob("*.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            card = manifest.get("card", {})
            key = (card.get("name"), card.get("year"))
            if key in EXPECTED:
                cls.cards[key] = (manifest, path)

    def test_all_captured_cards_are_bundled(self):
        self.assertEqual(set(self.cards), set(EXPECTED))

    def test_linked_height_and_full_card_studio_schema_are_preserved(self):
        for key, (overall, height_inches, theme, team, slot) in EXPECTED.items():
            with self.subTest(card=key):
                manifest, path = self.cards[key]
                card = manifest["card"]
                custom = card["customPlayerData"]
                self.assertEqual(card["overall"], overall)
                self.assertEqual(card["heightInches"], height_inches)
                self.assertEqual(round(custom["appearance"]["height_cm"] / 2.54), height_inches)
                self.assertEqual(card["theme"], theme)
                self.assertEqual(custom["sourceLiveTeam"], team)
                self.assertEqual(custom["sourceLiveSlot"], slot)
                self.assertTrue(custom["gearCaptureVerified"])
                self.assertEqual(len(card["attributes"]), 61)
                self.assertEqual(len(card["tendencies"]), 84)
                self.assertEqual(len(custom["signatures"]), 45)
                self.assertEqual(len(custom["gear"]), 24)
                self.assertEqual(len(card["hotZones"]), 14)
                art = path.with_suffix(".png")
                with Image.open(art) as image:
                    self.assertEqual(image.size, (325, 455))
                    self.assertEqual(image.format, "PNG")


if __name__ == "__main__":
    unittest.main()
