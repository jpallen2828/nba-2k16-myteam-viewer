"""Zoomable native-pixel card preview with accurate drag coordinates."""

from __future__ import annotations

import math

from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import QAbstractScrollArea, QSizePolicy


def pil_to_qimage(image: Image.Image) -> QImage:
    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    return QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888).copy()


def mask_to_qimage(mask: Image.Image) -> QImage:
    alpha = mask.convert("L")
    rgba = Image.new("RGBA", alpha.size, (255, 255, 255, 0))
    rgba.putalpha(alpha)
    return pil_to_qimage(rgba)


class CardCanvasWidget(QAbstractScrollArea):
    player_moved = Signal(float, float)
    nudge_requested = Signal(int, int)
    player_scale_requested = Signal(float)
    player_delete_requested = Signal()
    zoom_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(420, 520)
        self._image: QImage | None = None
        self._hit_mask: QImage | None = None
        self._zoom: float | None = None  # None means fit
        self._checkerboard = True
        self._dragging = False
        self._drag_offset = QPointF()
        self._player_position = QPointF()
        self.horizontalScrollBar().valueChanged.connect(self.viewport().update)
        self.verticalScrollBar().valueChanged.connect(self.viewport().update)

    def set_render(self, image: Image.Image, player_hit_mask: Image.Image | None, player_x: float, player_y: float) -> None:
        self._image = pil_to_qimage(image)
        self._hit_mask = mask_to_qimage(player_hit_mask) if player_hit_mask is not None else None
        self._player_position = QPointF(player_x, player_y)
        self._update_scrollbars()
        self.viewport().update()

    def set_checkerboard(self, enabled: bool) -> None:
        self._checkerboard = enabled
        self.viewport().update()

    def checkerboard_enabled(self) -> bool:
        return self._checkerboard

    def zoom_setting(self) -> str:
        return "fit" if self._zoom is None else str(self._zoom)

    def set_zoom_fit(self) -> None:
        self._zoom = None
        self._update_scrollbars()
        self.zoom_changed.emit("Fit")

    def set_zoom(self, scale: float) -> None:
        self._zoom = max(0.01, scale)
        self._update_scrollbars()
        self.zoom_changed.emit(f"{round(self._zoom * 100)}%")

    def zoom_in(self) -> None:
        levels = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
        current = self.effective_zoom()
        self.set_zoom(next((level for level in levels if level > current + 1e-6), levels[-1]))

    def zoom_out(self) -> None:
        levels = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
        current = self.effective_zoom()
        self.set_zoom(next((level for level in reversed(levels) if level < current - 1e-6), levels[0]))

    def effective_zoom(self) -> float:
        if self._zoom is not None:
            return self._zoom
        if self._image is None:
            return 1.0
        margin = 32
        return max(
            0.01,
            min(
                (self.viewport().width() - margin) / self._image.width(),
                (self.viewport().height() - margin) / self._image.height(),
            ),
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._update_scrollbars()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self.viewport())
        painter.fillRect(self.viewport().rect(), QColor("#10151d"))
        if self._image is None:
            painter.setPen(QColor("#9ba9ba"))
            painter.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter, "No template render available")
            return
        rect = self._draw_rect()
        if self._checkerboard:
            self._paint_checkerboard(painter, rect)
        else:
            painter.fillRect(rect, QColor("#252c36"))
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.effective_zoom() < 2.0)
        painter.drawImage(rect, self._image)
        painter.setPen(QColor("#52657c"))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            native = self._native_point(event.position())
            if native is not None and self._player_hit(native):
                self._dragging = True
                self._drag_offset = self._player_position - native
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if self._dragging:
            native = self._native_point(event.position(), clamp=False)
            if native is not None:
                position = native + self._drag_offset
                self._player_position = position
                self.player_moved.emit(position.x(), position.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        if event.key() == Qt.Key.Key_Delete:
            self.player_delete_requested.emit()
            event.accept()
            return
        delta = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        moves = {
            Qt.Key.Key_Left: (-delta, 0),
            Qt.Key.Key_Right: (delta, 0),
            Qt.Key.Key_Up: (0, -delta),
            Qt.Key.Key_Down: (0, delta),
        }
        if event.key() in moves:
            self.nudge_requested.emit(*moves[event.key()])
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt API
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                # Most wheels report 120 units per notch. Exponential scaling
                # also handles high-resolution trackpad deltas smoothly.
                self.player_scale_requested.emit(1.01 ** (delta / 120.0))
                event.accept()
                return
        super().wheelEvent(event)

    def _player_hit(self, native: QPointF) -> bool:
        if self._hit_mask is None:
            return False
        x, y = math.floor(native.x()), math.floor(native.y())
        if x < 0 or y < 0 or x >= self._hit_mask.width() or y >= self._hit_mask.height():
            return False
        return QColor(self._hit_mask.pixel(x, y)).alpha() > 0 or QColor(self._hit_mask.pixel(x, y)).red() > 0

    def _native_point(self, point: QPointF, clamp: bool = True) -> QPointF | None:
        if self._image is None:
            return None
        rect = self._draw_rect()
        if clamp and not rect.contains(point):
            return None
        scale = self.effective_zoom()
        return QPointF((point.x() - rect.left()) / scale, (point.y() - rect.top()) / scale)

    def _draw_rect(self) -> QRectF:
        if self._image is None:
            return QRectF()
        scale = self.effective_zoom()
        width, height = self._image.width() * scale, self._image.height() * scale
        left = (self.viewport().width() - width) / 2 if width <= self.viewport().width() else -self.horizontalScrollBar().value()
        top = (self.viewport().height() - height) / 2 if height <= self.viewport().height() else -self.verticalScrollBar().value()
        return QRectF(left, top, width, height)

    def _update_scrollbars(self) -> None:
        if self._image is None:
            return
        scale = self.effective_zoom()
        width, height = round(self._image.width() * scale), round(self._image.height() * scale)
        self.horizontalScrollBar().setRange(0, max(0, width - self.viewport().width()))
        self.verticalScrollBar().setRange(0, max(0, height - self.viewport().height()))
        self.horizontalScrollBar().setPageStep(self.viewport().width())
        self.verticalScrollBar().setPageStep(self.viewport().height())
        self.viewport().update()

    @staticmethod
    def _paint_checkerboard(painter: QPainter, rect: QRectF) -> None:
        tile = 12
        painter.save()
        painter.setClipRect(rect)
        x0, y0 = math.floor(rect.left()), math.floor(rect.top())
        x1, y1 = math.ceil(rect.right()), math.ceil(rect.bottom())
        colors = (QColor("#d9dde2"), QColor("#aeb6c0"))
        for y in range(y0, y1, tile):
            for x in range(x0, x1, tile):
                painter.fillRect(x, y, tile, tile, colors[((x - x0) // tile + (y - y0) // tile) & 1])
        painter.restore()
