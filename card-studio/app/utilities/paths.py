"""Filesystem paths with strict separation from the MyTEAM companion app."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def project_root() -> Path:
    """Return the source/bundle root without relying on the working directory."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def user_data_root() -> Path:
    """Return Card Studio's independent writable data directory."""
    override = os.environ.get("NBA2K16_CARD_STUDIO_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "NBA2K16CardStudio"


def background_removal_model_root() -> Path:
    """Locate the side-by-side model folder in source and portable builds."""
    if getattr(sys, "frozen", False):
        sidecar = Path(sys.executable).resolve().parent / "models"
        if sidecar.is_dir():
            return sidecar
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            bundled = Path(bundle_root) / "models"
            if bundled.is_dir():
                return bundled
        return sidecar
    return project_root() / "models"


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Resolved application resource and writable directories."""

    root: Path
    templates: Path
    readme: Path
    user_data: Path
    projects: Path
    exports: Path
    logs: Path
    builder_projects: Path
    builder_autosaves: Path
    builder_backups: Path

    @classmethod
    def create(cls) -> "AppPaths":
        root = project_root()
        data = user_data_root()
        result = cls(
            root=root,
            templates=root / "assets" / "built_in_templates",
            readme=root / "README.md",
            user_data=data,
            projects=data / "projects",
            exports=data / "exports",
            logs=data / "logs",
            builder_projects=data / "builder-projects",
            builder_autosaves=data / "builder-autosaves",
            builder_backups=data / "builder-backups",
        )
        result.ensure_writable_directories()
        return result

    def ensure_writable_directories(self) -> None:
        for directory in (
            self.user_data,
            self.projects,
            self.exports,
            self.logs,
            self.builder_projects,
            self.builder_autosaves,
            self.builder_backups,
        ):
            directory.mkdir(parents=True, exist_ok=True)
