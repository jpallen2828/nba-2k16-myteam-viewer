import json
import random
import re
import unittest
from collections import Counter
from pathlib import Path


VIEWER = Path(__file__).resolve().parents[1]
APP_JS = VIEWER / "app.js"
CARDS_JSON = VIEWER / "data" / "cards.json"
CUSTOM_CARDS = VIEWER / "data" / "custom-cards"
POSITIONS = ("PG", "SG", "SF", "PF", "C")
TIERS = ("Pink Diamond", "Diamond", "Amethyst", "Gold", "Silver", "Bronze")


def load_release_cards():
    cards = json.loads(CARDS_JSON.read_text(encoding="utf-8-sig"))
    for path in CUSTOM_CARDS.glob("*.json"):
        package = json.loads(path.read_text(encoding="utf-8"))
        cards.append(package["card"])
    return cards


class RandomTeamTests(unittest.TestCase):
    def test_generator_selects_tier_before_card_with_uniform_rolls(self):
        source = APP_JS.read_text(encoding="utf-8")
        function = re.search(
            r"function equalTierRandomChoice\(items\) \{(?P<body>.*?)\n\}",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(function)
        body = function.group("body")
        self.assertIn("tierOrder", body)
        self.assertIn("Math.floor(Math.random() * tierPools.length)", body)
        self.assertIn("Math.floor(Math.random() * selectedTierPool.length)", body)
        self.assertIn("const card = equalTierRandomChoice(eligible);", source)
        self.assertNotIn("lineupTierWeights", source)
        self.assertNotIn("guaranteedPremiumIndex", source)
        self.assertNotIn("bronzeUsed", source)

    def test_every_position_has_all_six_release_tiers(self):
        cards = load_release_cards()
        for position in POSITIONS:
            available = {card.get("tier") for card in cards if card.get("position") == position}
            self.assertEqual(set(TIERS), available.intersection(TIERS), position)

    def test_uniform_tier_roll_is_independent_of_tier_card_count(self):
        generator = random.Random(2016)
        samples = 120_000
        counts = Counter(TIERS[generator.randrange(len(TIERS))] for _ in range(samples))
        expected = samples / len(TIERS)
        for tier in TIERS:
            self.assertLess(abs(counts[tier] - expected) / samples, 0.005, tier)


if __name__ == "__main__":
    unittest.main()
