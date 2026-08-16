"""Qt settings isolated under NBA2K16Tools/NBA2K16CardStudio."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSettings

from app.constants import ORGANIZATION_NAME, SETTINGS_APPLICATION_NAME


class SettingsService:
    def __init__(self) -> None:
        self.settings = QSettings(ORGANIZATION_NAME, SETTINGS_APPLICATION_NAME)

    def value(self, key: str, default=None):
        return self.settings.value(key, default)

    def set_value(self, key: str, value) -> None:
        self.settings.setValue(key, value)

    def restore_geometry(self) -> QByteArray | None:
        value = self.settings.value("window/geometry")
        return value if isinstance(value, QByteArray) else None

    def save_geometry(self, value: QByteArray) -> None:
        self.settings.setValue("window/geometry", value)
