"""Offline MyTEAM player presets and canonical theme/collection choices."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PlayerPresetDatabase:
    presets: tuple[dict, ...] = ()
    themes: tuple[str, ...] = ()
    collections: tuple[str, ...] = ()
    theme_collections: dict[str, tuple[str, ...]] | None = None

    @classmethod
    def load(cls, path: Path) -> "PlayerPresetDatabase":
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, json.JSONDecodeError):
            return cls()
        if payload.get("schema") != "nba2k16.card-studio-player-presets/v1":
            return cls()
        mapping = {
            str(theme): tuple(str(value) for value in values if value)
            for theme, values in (payload.get("themeCollections") or {}).items()
            if isinstance(values, list)
        }
        return cls(
            presets=tuple(item for item in payload.get("presets", []) if isinstance(item, dict)),
            themes=tuple(str(value) for value in payload.get("themes", []) if value),
            collections=tuple(str(value) for value in payload.get("collections", []) if value),
            theme_collections=mapping,
        )
