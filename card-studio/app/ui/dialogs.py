"""Consistent user-facing dialogs."""

from PySide6.QtWidgets import QMessageBox, QWidget


def show_error(parent: QWidget, title: str, message: str, details: str | None = None) -> None:
    box = QMessageBox(QMessageBox.Icon.Critical, title, message, parent=parent)
    if details:
        box.setDetailedText(details)
    box.exec()


def show_information(parent: QWidget, title: str, message: str) -> None:
    QMessageBox.information(parent, title, message)


def confirm_discard(parent: QWidget) -> bool:
    result = QMessageBox.question(
        parent,
        "Unsaved changes",
        "Save changes before continuing?",
        QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Save,
    )
    parent.setProperty("discardDecision", int(result))
    return result != QMessageBox.StandardButton.Cancel
