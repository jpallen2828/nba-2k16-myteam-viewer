from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from app.services.logo_service import LOGO_CATEGORIES, LogoService


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "team_logos"


def test_all_recovered_logo_assets_are_bundled_by_category():
    service = LogoService(ASSETS)
    expected = {"current": 31, "historic": 46, "euroleague": 25}
    assert [category for category, _label in LOGO_CATEGORIES] == ["current", "historic", "euroleague"]
    for category, count in expected.items():
        assets = service.discover(category)
        assert len(assets) == count
        assert all(asset.path.is_file() for asset in assets)
        assert all(asset.asset_id != "Contact Sheet.png" for asset in assets)


def test_logo_manifest_proves_byte_identical_source_copies():
    manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["total_logo_count"] == 102
    assert len(manifest["excluded_non_logo_files"]) == 2
    for category_id, category in manifest["categories"].items():
        for record in category["assets"]:
            installed = ASSETS / category_id / record["asset_id"]
            assert sha256(installed.read_bytes()).hexdigest().upper() == record["sha256"]


def test_logo_service_loads_native_rgba_without_modifying_asset():
    service = LogoService(ASSETS)
    image = service.load("current", "Atlanta Hawks.png")
    assert image.mode == "RGBA"
    assert image.size == (1024, 1024)
