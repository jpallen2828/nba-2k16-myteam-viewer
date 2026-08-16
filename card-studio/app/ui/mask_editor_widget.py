"""Focused alpha-mask painting canvas; it never modifies source RGB pixels."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QWidget

from app.background_removal.cutout_service import apply_alpha_mask


def _qimage(image: Image.Image) -> QImage:
    rgba = image.convert("RGBA")
    raw = rgba.tobytes("raw", "RGBA")
    return QImage(raw, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888).copy()


class MaskEditorWidget(QWidget):
    mask_changed = Signal()

    def __init__(self, original: Image.Image, automatic_mask: Image.Image, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(620, 520)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.original = original.convert("RGBA").copy()
        self.automatic_mask = automatic_mask.convert("L").copy()
        self.mask = self.automatic_mask.copy()
        self._undo: list[Image.Image] = []
        self._redo: list[Image.Image] = []
        self.brush_mode = "restore"
        self.brush_size = 40
        self.brush_opacity = 1.0
        self.soft_edge = True
        self.view_mode = "cutout"
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self._painting = False
        self._panning = False
        self._last_image_point: QPointF | None = None
        self._last_pan_point: QPointF | None = None

    def current_mask(self) -> Image.Image:
        return self.mask.copy()

    def is_modified(self) -> bool:
        return not np.array_equal(np.asarray(self.mask), np.asarray(self.automatic_mask))

    def set_view_mode(self, mode: str) -> None:
        self.view_mode = mode
        self.update()

    def set_brush(self, mode: str, size: int, opacity: float, soft: bool) -> None:
        self.brush_mode = mode
        self.brush_size = max(1, int(size))
        self.brush_opacity = max(0.01, min(1.0, float(opacity)))
        self.soft_edge = soft

    def undo(self) -> None:
        if not self._undo:
            return
        self._redo.append(self.mask.copy())
        self.mask = self._undo.pop()
        self.mask_changed.emit()
        self.update()

    def redo(self) -> None:
        if not self._redo:
            return
        self._undo.append(self.mask.copy())
        self.mask = self._redo.pop()
        self.mask_changed.emit()
        self.update()

    def reset_automatic(self) -> None:
        if np.array_equal(np.asarray(self.mask), np.asarray(self.automatic_mask)):
            return
        self._undo.append(self.mask.copy())
        self._redo.clear()
        self.mask = self.automatic_mask.copy()
        self.mask_changed.emit()
        self.update()

    def replace_from_automatic(self, mask: Image.Image) -> None:
        self._undo.append(self.mask.copy())
        self._redo.clear()
        self.mask = mask.convert("L").copy()
        self.mask_changed.emit()
        self.update()

    def set_actual_pixels(self) -> None:
        fit = self._fit_scale()
        self.zoom = 1.0 / fit if fit > 0 else 1.0
        self.pan = QPointF(0, 0)
        self.update()

    def fit_view(self) -> None:
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#10151d"))
        display = self._display_image()
        target = self._target_rect()
        if self.view_mode in {"cutout", "overlay"}:
            self._paint_checkerboard(painter, target)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.zoom < 6.0)
        painter.drawImage(target, _qimage(display))
        if self._last_image_point is not None and not self._panning:
            screen = self._image_to_screen(self._last_image_point)
            radius = self.brush_size * self._target_rect().width() / self.original.width / 2.0
            painter.setPen(QPen(QColor("white"), 1))
            painter.drawEllipse(screen, radius, radius)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._last_pan_point = event.position()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.view_mode != "original":
            point = self._screen_to_image(event.position())
            if point is not None:
                self._undo.append(self.mask.copy())
                self._redo.clear()
                self._painting = True
                self._last_image_point = point
                self._dab(point.x(), point.y())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._panning and self._last_pan_point is not None:
            delta = event.position() - self._last_pan_point
            self.pan += delta
            self._last_pan_point = event.position()
            self.update()
            return
        point = self._screen_to_image(event.position())
        if point is not None:
            if self._painting and self._last_image_point is not None:
                self._stroke(self._last_image_point, point)
            self._last_image_point = point
        else:
            self._last_image_point = None
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._painting:
            self._painting = False
            self.mask_changed.emit()
            event.accept()
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self._last_pan_point = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta:
            self.zoom = max(0.1, min(20.0, self.zoom * (1.15 ** (delta / 120.0))))
            self.update()
            event.accept()
            return
        super().wheelEvent(event)

    def _stroke(self, start: QPointF, end: QPointF) -> None:
        distance = math.hypot(end.x() - start.x(), end.y() - start.y())
        steps = max(1, math.ceil(distance / max(1.0, self.brush_size / 5.0)))
        for index in range(1, steps + 1):
            t = index / steps
            self._dab(start.x() + (end.x() - start.x()) * t, start.y() + (end.y() - start.y()) * t)

    def _dab(self, center_x: float, center_y: float) -> None:
        values = np.asarray(self.mask, dtype=np.uint8).copy()
        radius = max(0.5, self.brush_size / 2.0)
        x0, x1 = max(0, int(center_x - radius - 1)), min(values.shape[1], int(center_x + radius + 2))
        y0, y1 = max(0, int(center_y - radius - 1)), min(values.shape[0], int(center_y + radius + 2))
        yy, xx = np.ogrid[y0:y1, x0:x1]
        distance = np.sqrt((xx - center_x) ** 2 + (yy - center_y) ** 2)
        influence = (distance <= radius).astype(np.float32)
        if self.soft_edge:
            influence *= np.clip(1.0 - distance / radius, 0.0, 1.0)
        influence *= self.brush_opacity
        target = 255.0 if self.brush_mode == "restore" else 0.0
        region = values[y0:y1, x0:x1].astype(np.float32)
        values[y0:y1, x0:x1] = np.rint(region + (target - region) * influence).astype(np.uint8)
        self.mask = Image.fromarray(values, mode="L")
        self.update()

    def _display_image(self) -> Image.Image:
        if self.view_mode == "original":
            return self.original
        if self.view_mode == "mask":
            return self.mask.convert("RGBA")
        cutout = apply_alpha_mask(self.original, self.mask)
        if self.view_mode == "overlay":
            rgb = np.asarray(self.original.convert("RGBA"), dtype=np.uint8).copy()
            alpha = np.asarray(self.mask, dtype=np.uint8)
            removed = (255 - alpha).astype(np.float32) / 255.0 * 0.65
            rgb[:, :, 0] = np.maximum(rgb[:, :, 0], np.rint(255 * removed).astype(np.uint8))
            rgb[:, :, 1] = np.rint(rgb[:, :, 1] * (1.0 - removed)).astype(np.uint8)
            rgb[:, :, 2] = np.rint(rgb[:, :, 2] * (1.0 - removed)).astype(np.uint8)
            return Image.fromarray(rgb, mode="RGBA")
        return cutout

    def _fit_scale(self) -> float:
        return min(max(1, self.width() - 20) / self.original.width, max(1, self.height() - 20) / self.original.height)

    def _target_rect(self) -> QRectF:
        scale = self._fit_scale() * self.zoom
        width, height = self.original.width * scale, self.original.height * scale
        return QRectF((self.width() - width) / 2 + self.pan.x(), (self.height() - height) / 2 + self.pan.y(), width, height)

    def _screen_to_image(self, point: QPointF) -> QPointF | None:
        target = self._target_rect()
        if not target.contains(point):
            return None
        return QPointF((point.x() - target.left()) * self.original.width / target.width(), (point.y() - target.top()) * self.original.height / target.height())

    def _image_to_screen(self, point: QPointF) -> QPointF:
        target = self._target_rect()
        return QPointF(target.left() + point.x() * target.width() / self.original.width, target.top() + point.y() * target.height() / self.original.height)

    @staticmethod
    def _paint_checkerboard(painter: QPainter, target: QRectF) -> None:
        painter.save()
        painter.setClipRect(target)
        cell = 12
        for y in range(int(target.top()), int(target.bottom()) + cell, cell):
            for x in range(int(target.left()), int(target.right()) + cell, cell):
                color = QColor("#c7ccd2") if ((x // cell) + (y // cell)) % 2 else QColor("#8e969f")
                painter.fillRect(x, y, cell, cell, color)
        painter.restore()
