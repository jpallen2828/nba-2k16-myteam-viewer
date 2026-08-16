import json
from pathlib import Path

import pytest

from app.models.player_art_model import PlayerTransform
from app.models.card_assets_model import CardAssetSelection
from app.models.logo_model import LogoPlacement
from app.models.project_model import CardProject, TemplateReference
from app.models.project_model import BackgroundRemovalState
from app.services.project_service import ProjectService
from app.utilities.validation import ProjectFormatError


def make_project(player_path: Path | None = None) -> CardProject:
    return CardProject(
        template=TemplateReference("development_tier", "../templates/development_tier"),
        player_source_path=str(player_path) if player_path else None,
        player_transform=PlayerTransform(123.5, 456.0, 1.25, -12.5, True),
    )


def test_project_saves_and_reloads_transform(tmp_path):
    source = tmp_path / "player.png"
    source.write_bytes(b"placeholder")
    project = make_project(source)
    path = tmp_path / "test.2k16card"
    ProjectService.save(project, path)
    loaded = ProjectService.load(path)
    assert loaded.player_transform == project.player_transform
    assert Path(loaded.player_source_path) == source
    assert loaded.modified is False


def test_project_saves_and_reloads_card_asset_selections(tmp_path):
    project = make_project()
    project.logo = LogoPlacement("historic", "1995-96 Chicago Bulls.png")
    project.card_assets = CardAssetSelection("theme_historic", "historic_players")
    path = tmp_path / "logo.2k16card"
    ProjectService.save(project, path)
    loaded = ProjectService.load(path)
    assert loaded.logo == project.logo
    assert loaded.card_assets == project.card_assets


def test_project_saves_and_reloads_background_removal_mask(tmp_path):
    project = make_project()
    project.background_removal = BackgroundRemovalState(
        enabled=True,
        accepted_mask_png="YWNjZXB0ZWQ=",
        automatic_mask_png="YXV0b21hdGlj",
        model_name="BiRefNet General Lite",
        model_version="epoch 232",
        postprocessing={"threshold": 8, "edge_softness": 0.5},
        manually_edited=True,
    )
    path = tmp_path / "mask.2k16card"
    ProjectService.save(project, path)
    loaded = ProjectService.load(path)
    assert loaded.background_removal == project.background_removal


def test_unsupported_project_version_fails(tmp_path):
    path = tmp_path / "future.2k16card"
    path.write_text(json.dumps({"project_version": 99}), encoding="utf-8")
    with pytest.raises(ProjectFormatError, match="Unsupported project_version"):
        ProjectService.load(path)


def test_missing_player_path_is_reported_without_load_failure(tmp_path):
    project = make_project(tmp_path / "missing.png")
    path = tmp_path / "missing.2k16card"
    ProjectService.save(project, path)
    loaded = ProjectService.load(path)
    assert ProjectService.missing_player_path(loaded) == tmp_path / "missing.png"
