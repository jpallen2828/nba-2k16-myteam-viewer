#!/usr/bin/env python3
"""Developer-only Version 1/Version 2/live-fixture comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.player_data.overall_calculator import OverallCalculator  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=ROOT / "tests" / "fixtures" / "overall_v2_live_holdout.json")
    args = parser.parse_args()
    calculator = OverallCalculator.load_default()
    rows = json.loads(args.fixtures.read_text(encoding="utf-8"))["fixtures"]
    print("sample_id\tposition\tlive\tv1\tv2\tv1_delta\tv2_delta")
    for row in rows:
        v1 = calculator.estimate_v1(row["position"], row["attributes"])
        v2 = calculator.estimate(
            row["position"], row["attributes"],
            height_inches=row["height_inches"], durability=row["durability"],
        )
        live = int(row["displayed_overall"])
        print(f"{row['sample_id']}\t{row['position']}\t{live}\t{v1.overall}\t{v2.overall}\t{v1.overall-live:+d}\t{v2.overall-live:+d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
