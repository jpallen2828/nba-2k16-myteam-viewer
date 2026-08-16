"""Atomic Builder project persistence with independent backups."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.builder.models import BuilderProject, utc_now
from app.constants import BUILDER_PROJECT_EXTENSION


class BuilderProjectError(ValueError):
    pass


class BuilderProjectService:
    def __init__(self, backup_root: Path | None = None) -> None:
        self.backup_root = backup_root

    def save(self, project: BuilderProject, path: Path, *, backup: bool = True) -> Path:
        path = path.resolve()
        if path.suffix.lower() != BUILDER_PROJECT_EXTENSION:
            path = path.with_suffix(BUILDER_PROJECT_EXTENSION)
        path.parent.mkdir(parents=True, exist_ok=True)
        if backup and path.exists():
            self._backup(path)
        project.modified_at = utc_now()
        payload = project.to_dict(path.parent)
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            # Parse before replacing the last valid file.
            json.loads(temporary.read_text(encoding="utf-8"))
            temporary.replace(path)
        except (OSError, TypeError, ValueError) as exc:
            temporary.unlink(missing_ok=True)
            raise BuilderProjectError(f"Could not save Builder project: {exc}") from exc
        project.file_path = path
        project.modified = False
        return path

    def load(self, path: Path) -> BuilderProject:
        path = path.resolve()
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            project = BuilderProject.from_dict(data, path.parent)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise BuilderProjectError(f"Could not load Builder project: {exc}") from exc
        project.file_path = path
        return project

    def _backup(self, path: Path) -> None:
        directory = self.backup_root or path.parent / "backups"
        directory.mkdir(parents=True, exist_ok=True)
        stamp = path.stat().st_mtime_ns
        target = directory / f"{path.stem}-{stamp}{path.suffix}.bak"
        shutil.copy2(path, target)
        backups = sorted(directory.glob(f"{path.stem}-*{path.suffix}.bak"), key=lambda item: item.stat().st_mtime_ns)
        for old in backups[:-10]:
            old.unlink(missing_ok=True)

    @staticmethod
    def missing_sources(project: BuilderProject) -> list[SourceCard]:
        return [source for source in project.sources if not Path(source.path).is_file()]
