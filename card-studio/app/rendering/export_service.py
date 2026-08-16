"""Exact-size, lossless PNG export and verification."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.utilities.validation import ExportError


class ExportService:
    @staticmethod
    def export_png(image: Image.Image, path: Path, expected_size: tuple[int, int]) -> Path:
        try:
            rgba = image.convert("RGBA")
            if rgba.size != expected_size:
                raise ExportError(f"Renderer returned {rgba.size}; expected {expected_size}.")
            path.parent.mkdir(parents=True, exist_ok=True)
            rgba.save(path, format="PNG", optimize=False)
            ExportService.verify_png(path, expected_size)
        except ExportError:
            raise
        except OSError as exc:
            raise ExportError(f"Could not export PNG to '{path}': {exc}") from exc
        return path

    @staticmethod
    def verify_png(path: Path, expected_size: tuple[int, int]) -> None:
        try:
            with Image.open(path) as opened:
                opened.load()
                if opened.format != "PNG":
                    raise ExportError("Exported file is not a PNG.")
                if opened.size != expected_size:
                    raise ExportError(f"Exported PNG is {opened.size}; expected {expected_size}.")
                if opened.mode != "RGBA":
                    raise ExportError(f"Exported PNG mode is {opened.mode}; expected RGBA.")
        except OSError as exc:
            raise ExportError(f"Could not verify exported PNG: {exc}") from exc
