"""Crash-recovery autosaves that never overwrite source cards or valid saves."""

from __future__ import annotations

import json
from pathlib import Path

from app.builder.models import BuilderProject
from app.builder.services.project_service import BuilderProjectError


class AutosaveService:
    def __init__(self, autosave_root: Path) -> None:
        self.root = autosave_root
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def recovery_path(self) -> Path:
        return self.root / "template-builder-recovery.2k16templatework"

    def write(self, project: BuilderProject) -> Path:
        target = self.recovery_path
        temporary = target.with_suffix(target.suffix + ".tmp")
        try:
            # Recovery lives outside the project folder, so retain absolute
            # source references rather than creating misleading relative paths.
            payload = project.to_dict(None)
            temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            json.loads(temporary.read_text(encoding="utf-8"))
            temporary.replace(target)
        except (OSError, ValueError, TypeError) as exc:
            temporary.unlink(missing_ok=True)
            raise BuilderProjectError(f"Could not write recovery data: {exc}") from exc
        return target

    def load(self) -> BuilderProject:
        path = self.recovery_path
        try:
            project = BuilderProject.from_dict(json.loads(path.read_text(encoding="utf-8-sig")), path.parent)
            project.modified = True
            return project
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise BuilderProjectError(f"Recovery data is invalid: {exc}") from exc

    def available(self) -> bool:
        return self.recovery_path.is_file()

    def clear(self) -> None:
        self.recovery_path.unlink(missing_ok=True)
