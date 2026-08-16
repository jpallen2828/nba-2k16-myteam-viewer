"""Versioned .2k16card JSON persistence with relocatable paths."""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.constants import PROJECT_FORMAT_VERSION
from app.models.project_model import CardProject, utc_now
from app.utilities.validation import ProjectFormatError


class ProjectService:
    @staticmethod
    def save(project: CardProject, path: Path) -> Path:
        path = path.resolve()
        project.date_modified = utc_now()
        data = project.to_dict()
        template_path = Path(project.template.path) if project.template.path else None
        if template_path and template_path.is_absolute():
            try:
                data["template"]["path"] = Path(os.path.relpath(template_path.resolve(), path.parent)).as_posix()
            except ValueError:  # Different Windows drives cannot be relativized.
                data["template"]["path"] = str(template_path.resolve())
        source = project.player_source_path
        if source:
            source_path = Path(source)
            if source_path.is_absolute():
                try:
                    data["player"]["source_path"] = Path(os.path.relpath(source_path.resolve(), path.parent)).as_posix()
                except ValueError:  # Different Windows drives cannot be relativized.
                    data["player"]["source_path"] = str(source_path.resolve())
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            raise ProjectFormatError(f"Could not save project '{path}': {exc}") from exc
        project.file_path = path
        project.modified = False
        return path

    @staticmethod
    def load(path: Path) -> CardProject:
        path = path.resolve()
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectFormatError(f"Could not open project '{path}': {exc}") from exc
        version = data.get("project_version")
        if version != PROJECT_FORMAT_VERSION:
            raise ProjectFormatError(
                f"Unsupported project_version {version!r}; supported version is {PROJECT_FORMAT_VERSION}."
            )
        project = CardProject.from_dict(data)
        if not project.template.template_id and not project.template.path:
            raise ProjectFormatError("Project does not identify a template.")
        source = project.player_source_path
        if source:
            source_path = Path(source)
            if not source_path.is_absolute():
                source_path = (path.parent / source_path).resolve()
            project.player_source_path = str(source_path)
        project.file_path = path
        project.modified = False
        return project

    @staticmethod
    def missing_player_path(project: CardProject) -> Path | None:
        if not project.player_source_path:
            return None
        path = Path(project.player_source_path)
        return None if path.is_file() else path
