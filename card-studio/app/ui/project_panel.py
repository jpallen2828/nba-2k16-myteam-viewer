"""Compact project and template summary panel."""

from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout, QWidget


class ProjectPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        project = QGroupBox("Project")
        project_layout = QVBoxLayout(project)
        self.project_name = QLabel("Untitled.2k16card")
        self.project_name.setWordWrap(True)
        self.template_name = QLabel("Template: —")
        self.template_name.setWordWrap(True)
        self.canvas_size = QLabel("Native size: —")
        self.instruction = QLabel("Import a transparent player PNG to begin.")
        self.instruction.setWordWrap(True)
        project_layout.addWidget(self.project_name)
        project_layout.addWidget(self.template_name)
        project_layout.addWidget(self.canvas_size)
        project_layout.addSpacing(12)
        project_layout.addWidget(self.instruction)
        layout.addWidget(project)

    def update_project(self, filename: str, template_name: str, size: tuple[int, int], modified: bool) -> None:
        self.project_name.setText(("● " if modified else "") + filename)
        self.template_name.setText(f"Template: {template_name}")
        self.canvas_size.setText(f"Native size: {size[0]} x {size[1]} px")

    def set_instruction(self, text: str) -> None:
        self.instruction.setText(text)
