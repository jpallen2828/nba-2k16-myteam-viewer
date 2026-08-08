#!/usr/bin/env python3
"""Audit draft odds and Pink Diamond override behavior for the MyTEAM viewer."""

from __future__ import annotations

import json
import math
import random
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "app.js"
CARDS_JSON = ROOT / "data" / "cards.json"
LOCAL_CUSTOM_ROOT = Path("C:/Users/James/AppData/Local/NBA2K16MyTEAMViewer/custom-cards")
LINEUP_POSITIONS = ["PG", "SG", "SF", "PF", "C"]
TEST_ITERATIONS = 200_000


TARGET_CARDS = {
    "1227118467": {"name": "Wilt Chamberlain", "overall": 99, "year": 1962},
}


def parse_js_object(text: str) -> dict:
    block = re.search(r"const draftOddsByMode\s*=\s*(\{[\s\S]*?\});", text)
    if not block:
        raise RuntimeError("Could not locate draftOddsByMode block in app.js.")
    payload = block.group(1)
    payload = re.sub(r"(?m)(?<=\{|,)(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*):", r'\1"\2":', payload)
    payload = payload.replace("'", '"')
    payload = re.sub(r"(?<!\d)(\.\d+)", r"0\1", payload)
    return json.loads(payload)


def parse_override_ids(text: str) -> set[str]:
    match = re.search(r"draftPinkDiamondCardOverrides\s*=\s*new\s+Set\(\[(.*?)\]\);", text, re.S)
    if not match:
        raise RuntimeError("Could not locate draftPinkDiamondCardOverrides in app.js.")
    raw = match.group(1)
    ids = set()
    for value in raw.split(","):
        value = value.strip().strip("\"' ")
        if value:
            ids.add(value)
    return ids


def parse_display_percent(value: float) -> float:
    percent = value * 100
    if percent < 0.01:
        text = f"{percent:.3f}".rstrip("0").rstrip(".")
    elif percent < 1:
        text = f"{percent:.2f}".rstrip("0").rstrip(".")
    else:
        text = f"{percent:.1f}".rstrip("0").rstrip(".")
    return float(text)


def resolve_draft_tier(card: dict, overrides: set[str]) -> str | None:
    return "Pink Diamond" if str(card.get("id")) in overrides else card.get("tier")


def roll_tier(weights: list[list], roll: float) -> str:
    remaining = roll
    for tier, chance in weights:
        remaining -= chance
        if remaining < 0:
            return tier
    return weights[-1][0]


def expected_and_displayed(table: list[tuple[str, float]]) -> list[tuple[str, float, float, float]]:
    total = sum(chance for _, chance in table)
    return [
        (tier, chance, parse_display_percent(chance), chance / total if total else 0.0)
        for tier, chance in table
    ]


def load_custom_cards() -> list[dict]:
    if not LOCAL_CUSTOM_ROOT.exists():
        return []
    cards = []
    for path in LOCAL_CUSTOM_ROOT.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        card = payload.get("card", payload)
        if isinstance(card, dict):
            cards.append(card)
    return cards


def load_cards_for_audit() -> list[dict]:
    cards = json.loads(CARDS_JSON.read_text(encoding="utf-8"))
    cards.extend(load_custom_cards())
    return cards


def assert_almost(actual: float, expected: float, epsilon: float, label: str) -> None:
    delta = abs(actual - expected)
    if delta > epsilon:
        raise AssertionError(f"{label}: expected {expected:.12f}, got {actual:.12f}, delta={delta:.12f}")


def check_weights(odds: dict[str, list[list]]) -> None:
    for mode, tables in odds.items():
        for role, table in tables.items():
            if role not in {"starter", "backup", "bench"}:
                continue
            running = 1.0
            total = sum(chance for _, chance in table)
            assert_almost(total, 1.0, 1e-12, f"{mode} {role} total")
            for tier, chance in table:
                if chance < 0:
                    raise AssertionError(f"{mode} {role} has negative chance for {tier}")
                if chance > 1:
                    raise AssertionError(f"{mode} {role} has >1.0 chance for {tier}: {chance}")
                running -= chance
                if running < -1e-12:
                    raise AssertionError(f"{mode} {role} cumulative dropped below 0 before final tier.")
                if running > 1:
                    raise AssertionError(f"{mode} {role} cumulative invalid: {running}")
            print(f"\n{mode.title()} {role.title()}")
            for tier, raw, displayed, effective in expected_and_displayed([tuple(row) for row in table]):
                print(f"  {tier}: displayed={displayed:.3f}% internal={raw:.12f} effective={effective:.12f}")


def simulate_role(role: str, tables: dict[str, list[list]], mode: str, iterations: int) -> dict[str, int]:
    table = tables[mode][role]
    counts = Counter()
    random.seed(1337)
    for _ in range(iterations):
        tier = roll_tier(table, random.random())
        counts[tier] += 1
    return {tier: counts.get(tier, 0) for tier, _ in table}


def validate_role_distribution(role: str, tables: dict[str, list[list]], mode: str, iterations: int) -> None:
    table = tables[mode][role]
    expected = {tier: chance * iterations for tier, chance in table}
    observed = simulate_role(role, tables, mode, iterations)
    for tier, chance in table:
        delta = abs(observed[tier] - expected[tier])
        tolerance = max(2.5, math.sqrt(iterations * chance * (1 - chance)) * 5)
        if delta > tolerance:
            raise AssertionError(
                f"{mode}/{role}/{tier} failed Monte-Carlo check: observed={observed[tier]} "
                f"expected={expected[tier]:.2f} delta={delta:.2f} tolerance={tolerance:.2f}"
            )


def check_pool_inclusion(records: list[dict], overrides: set[str]) -> None:
    id_set = {str(card.get("id")): card for card in records if card.get("id") is not None}
    for card_id, spec in TARGET_CARDS.items():
        record = id_set.get(card_id)
        if not record:
            print(f"ERROR: target record {card_id} not found in current local card load path.")
            continue

        resolved = resolve_draft_tier(record, overrides)
        if resolved != "Pink Diamond":
            raise AssertionError(f"{card_id} resolved to '{resolved}', expected 'Pink Diamond'.")
        for tier in ("Diamond", "Amethyst", "Gold", "Silver", "Bronze"):
            if resolve_draft_tier(record, overrides) == tier:
                raise AssertionError(f"{card_id} unexpectedly resolves as '{tier}'.")
        if record.get("name") != spec["name"]:
            print(f"WARN: {card_id} name mismatch: db='{record.get('name')}', expected='{spec['name']}'.")
        if record.get("overall") != spec["overall"] or record.get("year") != spec["year"]:
            print(f"WARN: {card_id} has OVR={record.get('overall')} year={record.get('year')} but expected OVR={spec['overall']} year={spec['year']}.")

        for role in ("starter", "backup", "bench"):
            if role in {"starter", "backup"}:
                ok_position = bool(record.get("position") in LINEUP_POSITIONS)
                if not ok_position:
                    raise AssertionError(f"{card_id} has invalid lineup position '{record.get('position')}' for {role}/{role} slots.")
            else:
                ok_position = bool(record.get("position") in LINEUP_POSITIONS)
                if not ok_position:
                    raise AssertionError(f"{card_id} has invalid lineup position '{record.get('position')}' for bench slot.")
        print(f"PASS: {card_id} ({record.get('name')}) is explicitly mapped to Pink Diamond and remains draft-eligible for all slot types.")


def ensure_specific_id_overrides(overrides: set[str]) -> None:
    required = set(TARGET_CARDS)
    if not required.issubset(overrides):
        missing = required - overrides
        raise AssertionError(f"Missing required IDs from draft override set: {sorted(missing)}")


def main() -> int:
    app_text = APP_JS.read_text(encoding="utf-8")
    odds = parse_js_object(app_text)
    overrides = parse_override_ids(app_text)

    print(f"Draft pink overrides detected: {sorted(overrides)}")
    print(f"Target IDs confirmed required: {sorted(TARGET_CARDS)}")

    ensure_specific_id_overrides(overrides)
    check_weights(odds)

    for mode in ("baller", "default", "budget"):
        for role in ("starter", "backup", "bench"):
            validate_role_distribution(role, odds, mode, TEST_ITERATIONS)
            print(f"  PASS: Monte-Carlo {TEST_ITERATIONS} sample {mode}/{role}")

    records = load_cards_for_audit()
    check_pool_inclusion(records, overrides)

    # Exact Pink Diamond candidate checks using the resolved-tier helper and role-level filters.
    resolved_cards = [
        (record, resolve_draft_tier(record, overrides))
        for record in records
        if str(record.get("id")) in TARGET_CARDS
    ]
    if not resolved_cards:
        print("WARN: no target card records found in local card load; override is still present and active.")
    for role in ("starter", "backup", "bench"):
        for record, resolved in resolved_cards:
            if resolved != "Pink Diamond":
                raise AssertionError(f"Target card {record.get('id')} lost Pink Diamond resolution under role '{role}'.")
    print("\nDraft audit completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
