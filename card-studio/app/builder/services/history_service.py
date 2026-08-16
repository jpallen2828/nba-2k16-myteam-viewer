"""Snapshot history with grouped, descriptive Builder operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.builder.models import BuilderProject


@dataclass(slots=True)
class HistoryEntry:
    description: str
    before: dict
    after: dict


class HistoryService:
    def __init__(self, limit: int = 50) -> None:
        self.limit = max(1, limit)
        self._undo: list[HistoryEntry] = []
        self._redo: list[HistoryEntry] = []

    def record(self, description: str, before: dict, project: BuilderProject) -> None:
        self._undo.append(HistoryEntry(description, before, project.snapshot()))
        self._undo = self._undo[-self.limit:]
        self._redo.clear()
        project.mark_modified(description)

    def undo(self, current: BuilderProject) -> BuilderProject:
        if not self._undo:
            return current
        entry = self._undo.pop()
        self._redo.append(HistoryEntry(entry.description, entry.before, current.snapshot()))
        restored = BuilderProject.from_dict(entry.before, current.file_path.parent if current.file_path else None)
        restored.file_path = current.file_path
        restored.modified = True
        return restored

    def redo(self, current: BuilderProject) -> BuilderProject:
        if not self._redo:
            return current
        entry = self._redo.pop()
        restored = BuilderProject.from_dict(entry.after, current.file_path.parent if current.file_path else None)
        restored.file_path = current.file_path
        restored.modified = True
        self._undo.append(HistoryEntry(entry.description, current.snapshot(), entry.after))
        return restored

    def descriptions(self) -> list[str]:
        return [item.description for item in self._undo]

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)
