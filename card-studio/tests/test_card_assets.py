from pathlib import Path

from PIL import Image

from app.services.card_asset_service import PngCardAssetService, promotion_display_names


ROOT = Path(__file__).resolve().parents[1]


def test_all_supplied_backgrounds_are_discoverable_and_decodable():
    service = PngCardAssetService(ROOT / "assets" / "myteam_card_backgrounds" / "png")
    assets = service.discover()
    assert len(assets) == 11
    assert {asset.asset_id for asset in assets} == {
        "theme_99_club",
        "theme_consumable",
        "theme_current",
        "theme_dynamic",
        "theme_euroleague",
        "theme_historic",
        "theme_moments",
        "theme_playoffs",
        "theme_rewards",
        "theme_roty_dpoy",
        "theme_throwback",
    }
    assert all(service.load(asset.asset_id).size == (1024, 1024) for asset in assets)


def test_all_normalized_promotion_logos_are_discoverable_and_decodable():
    root = ROOT / "assets" / "myteam_promotion_logos" / "runtime" / "normalized"
    service = PngCardAssetService(root, promotion_display_names(root))
    assets = service.discover()
    assert len(assets) == 14
    assert {asset.asset_id for asset in assets} >= {
        "current_player", "dynamic_ratings", "fiba", "historic_players", "moments", "throwback", "usa_olympic"
    }
    assert all(service.load(asset.asset_id).size == (256, 256) for asset in assets)
    assert next(asset.display_name for asset in assets if asset.asset_id == "dpoy") == "Defensive Player of the Year"
    assert next(asset.display_name for asset in assets if asset.asset_id == "fiba") == "FIBA"


def test_assets_retain_alpha_and_original_source_files_are_not_rewritten():
    root = ROOT / "assets" / "myteam_promotion_logos" / "runtime" / "normalized"
    service = PngCardAssetService(root)
    for asset in service.discover():
        with Image.open(asset.path) as opened:
            assert "A" in opened.getbands()
