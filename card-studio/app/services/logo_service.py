"""Discovery and validated loading for packaged team-logo PNG assets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from app.utilities.validation import LogoAssetError


LOGO_CATEGORIES = (
    ("current", "Current"),
    ("historic", "Historic"),
    ("euroleague", "EuroLeague"),
)


@dataclass(frozen=True, slots=True)
class LogoAsset:
    category: str
    asset_id: str
    display_name: str
    path: Path


class LogoService:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def discover(self, category: str) -> tuple[LogoAsset, ...]:
        if category not in dict(LOGO_CATEGORIES):
            return ()
        directory = self.root / category
        if not directory.is_dir():
            return ()
        return tuple(
            LogoAsset(category, path.name, path.stem, path)
            for path in sorted(directory.glob("*.png"), key=lambda item: item.name.casefold())
            if path.name.casefold() != "contact sheet.png"
        )

    def resolve(self, category: str, asset_id: str) -> LogoAsset:
        wanted = str(asset_id or "")
        asset = next((item for item in self.discover(category) if item.asset_id == wanted), None)
        if asset is None:
            raise LogoAssetError(f"Bundled logo was not found: {category}/{wanted}")
        return asset

    def load(self, category: str, asset_id: str) -> Image.Image:
        asset = self.resolve(category, asset_id)
        try:
            with Image.open(asset.path) as opened:
                image = opened.convert("RGBA")
                image.load()
                return image.copy()
        except OSError as exc:
            raise LogoAssetError(f"Could not decode bundled logo '{asset.display_name}': {exc}") from exc
