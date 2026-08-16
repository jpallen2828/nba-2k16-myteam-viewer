"""Synchronize dynamic-text metadata and install all built-in tier packages."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

from extract_standard_tiers import text_layout


STUDIO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = STUDIO_ROOT / "assets" / "built_in_templates"
LEGACY_ROOT = STUDIO_ROOT / "templates"
ORDER = ("pink_diamond", "diamond", "amethyst", "gold", "silver", "bronze")
CORE_FILES = ("background.png", "foreground.png", "player_mask.png", "preview.png", "template.json")


def synchronize() -> None:
    # Diamond and Pink Diamond are maintained source packages. Install their
    # native layers first; the other four runtime packages are already emitted
    # directly by extract_standard_tiers.py.
    for template_id in ("diamond", "pink_diamond"):
        source = LEGACY_ROOT / template_id
        target = RUNTIME_ROOT / template_id
        target.mkdir(parents=True, exist_ok=True)
        for filename in CORE_FILES:
            shutil.copyfile(source / filename, target / filename)

    for sort_order, template_id in enumerate(ORDER):
        paths = [RUNTIME_ROOT / template_id / "template.json"]
        if template_id in {"diamond", "pink_diamond"}:
            paths.append(LEGACY_ROOT / template_id / "template.json")
        for path in paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["sort_order"] = sort_order
            # Stored per package so custom tier layouts remain data-driven.
            payload["text_fields"] = text_layout(template_id)
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    synchronize()
    print("Synchronized:", ", ".join(ORDER))
