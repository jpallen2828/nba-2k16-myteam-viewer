"""Discovery and validated loading for recovered MyTEAM card artwork."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from app.utilities.validation import CardAssetError


BACKGROUND_DISPLAY_NAMES = {
    "theme_99_club": "99 Club",
    "theme_consumable": "Consumable",
    "theme_current": "Current",
    "theme_dynamic": "Dynamic Ratings",
    "theme_euroleague": "EuroLeague",
    "theme_historic": "Historic",
    "theme_moments": "Moments",
    "theme_playoffs": "Playoffs",
    "theme_rewards": "Rewards",
    "theme_roty_dpoy": "ROTY / DPOY",
    "theme_throwback": "Throwback",
}


@dataclass(frozen=True, slots=True)
class CardAsset:
    asset_id: str
    display_name: str
    path: Path


class PngCardAssetService:
    def __init__(self, root: Path, display_names: dict[str, str] | None = None) -> None:
        self.root = Path(root).resolve()
        self.display_names = display_names or {}

    def discover(self) -> tuple[CardAsset, ...]:
        if not self.root.is_dir():
            return ()
        assets = []
        for path in sorted(self.root.glob("*.png"), key=lambda item: item.name.casefold()):
            asset_id = path.stem
            fallback = asset_id.removeprefix("theme_").replace("_", " ").title()
            assets.append(CardAsset(asset_id, self.display_names.get(asset_id, fallback), path))
        return tuple(assets)

    def resolve(self, asset_id: str) -> CardAsset:
        wanted = str(asset_id or "")
        asset = next((item for item in self.discover() if item.asset_id == wanted), None)
        if asset is None:
            raise CardAssetError(f"Bundled card asset was not found: {wanted}")
        return asset

    def load(self, asset_id: str) -> Image.Image:
        asset = self.resolve(asset_id)
        try:
            with Image.open(asset.path) as opened:
                image = opened.convert("RGBA")
                image.load()
                return image.copy()
        except OSError as exc:
            raise CardAssetError(f"Could not decode bundled card asset '{asset.display_name}': {exc}") from exc


def promotion_display_names(asset_root: Path) -> dict[str, str]:
    """Read the supplied recovery manifest without making it a runtime dependency."""
    manifest_path = Path(asset_root).resolve().parents[1] / "promotion_logos.json"
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {
        str(item.get("id")): str(item.get("display_name"))
        for item in data.get("logos", [])
        if item.get("id") and item.get("display_name")
    }
