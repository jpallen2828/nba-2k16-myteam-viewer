"""Serializable .2k16card project model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.constants import APPLICATION_NAME, PROJECT_FORMAT_VERSION
from app.models.card_assets_model import CardAssetSelection
from app.models.logo_model import LogoPlacement
from app.models.player_art_model import PlayerTransform
from app.player_data.schema import default_player_data, normalize_player_data
from app.text.normalization import normalize_name, normalize_overall, normalize_position


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class TemplateReference:
    template_id: str
    path: str


@dataclass(slots=True)
class TextPlaceholders:
    overall: str = ""
    position: str = ""
    name: str = ""
    style: str = "nba2k16_default"
    fitted_scale: dict[str, float] = field(default_factory=dict)
    fitted_tracking: dict[str, float] = field(default_factory=dict)
    offsets: dict[str, list[float]] = field(default_factory=dict)


@dataclass(slots=True)
class ExportPreferences:
    preserve_alpha: bool = True


@dataclass(slots=True)
class BackgroundRemovalState:
    enabled: bool = False
    accepted_mask_png: str = ""
    automatic_mask_png: str = ""
    model_name: str = ""
    model_version: str = ""
    postprocessing: dict[str, int | float] = field(default_factory=dict)
    manually_edited: bool = False

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "accepted_mask_png": self.accepted_mask_png,
            "automatic_mask_png": self.automatic_mask_png,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "postprocessing": self.postprocessing,
            "manually_edited": self.manually_edited,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "BackgroundRemovalState":
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", False)),
            accepted_mask_png=str(data.get("accepted_mask_png") or ""),
            automatic_mask_png=str(data.get("automatic_mask_png") or ""),
            model_name=str(data.get("model_name") or ""),
            model_version=str(data.get("model_version") or ""),
            postprocessing={
                str(key): value
                for key, value in (data.get("postprocessing") or {}).items()
                if isinstance(value, (int, float))
            },
            manually_edited=bool(data.get("manually_edited", False)),
        )


@dataclass(slots=True)
class CardProject:
    template: TemplateReference
    player_source_path: str | None
    player_transform: PlayerTransform
    logo: LogoPlacement = field(default_factory=LogoPlacement)
    card_assets: CardAssetSelection = field(default_factory=CardAssetSelection)
    text: TextPlaceholders = field(default_factory=TextPlaceholders)
    export_preferences: ExportPreferences = field(default_factory=ExportPreferences)
    background_removal: BackgroundRemovalState = field(default_factory=BackgroundRemovalState)
    player_data: dict = field(default_factory=default_player_data)
    project_version: int = PROJECT_FORMAT_VERSION
    application: str = APPLICATION_NAME
    date_created: str = field(default_factory=utc_now)
    date_modified: str = field(default_factory=utc_now)
    file_path: Path | None = None
    modified: bool = False

    def to_dict(self) -> dict:
        return {
            "project_version": self.project_version,
            "application": self.application,
            "template": {"id": self.template.template_id, "path": self.template.path},
            "player": {
                "source_path": self.player_source_path,
                **self.player_transform.to_dict(),
            },
            "logo": self.logo.to_dict(),
            "card_assets": self.card_assets.to_dict(),
            "text": {
                "overall": self.text.overall,
                "position": self.text.position,
                "name": self.text.name,
                "style": self.text.style,
                "fitted_scale": self.text.fitted_scale,
                "fitted_tracking": self.text.fitted_tracking,
                "offsets": self.text.offsets,
            },
            "export_preferences": {"preserve_alpha": self.export_preferences.preserve_alpha},
            "background_removal": self.background_removal.to_dict(),
            "player_data": normalize_player_data(self.player_data),
            "date_created": self.date_created,
            "date_modified": self.date_modified,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CardProject":
        template = data.get("template") or {}
        player = data.get("player") or {}
        text = data.get("text") or {}
        export = data.get("export_preferences") or {}
        logo = data.get("logo") or {}
        card_assets = data.get("card_assets") or {}
        return cls(
            project_version=int(data.get("project_version", 0)),
            application=str(data.get("application") or APPLICATION_NAME),
            template=TemplateReference(str(template.get("id") or ""), str(template.get("path") or "")),
            player_source_path=player.get("source_path"),
            player_transform=PlayerTransform.from_dict(player),
            logo=LogoPlacement.from_dict(logo),
            card_assets=CardAssetSelection.from_dict(card_assets),
            text=TextPlaceholders(
                overall=normalize_overall(text.get("overall")),
                position=normalize_position(text.get("position")),
                name=normalize_name(text.get("name")),
                style=str(text.get("style") or "nba2k16_default"),
                fitted_scale={str(key): float(value) for key, value in (text.get("fitted_scale") or {}).items()},
                fitted_tracking={str(key): float(value) for key, value in (text.get("fitted_tracking") or {}).items()},
                offsets={str(key): [float(number) for number in value[:2]] for key, value in (text.get("offsets") or {}).items() if isinstance(value, list)},
            ),
            export_preferences=ExportPreferences(bool(export.get("preserve_alpha", True))),
            background_removal=BackgroundRemovalState.from_dict(data.get("background_removal")),
            player_data=normalize_player_data(data.get("player_data")),
            date_created=str(data.get("date_created") or utc_now()),
            date_modified=str(data.get("date_modified") or utc_now()),
        )
