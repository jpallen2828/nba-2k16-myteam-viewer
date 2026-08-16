"""Nearest-neighbor Builder canvas with native-coordinate editing and pixel grid."""

from __future__ import annotations

import math

from PIL import Image
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QAbstractScrollArea, QSizePolicy

from app.ui.canvas_widget import pil_to_qimage


class BuilderCanvas(QAbstractScrollArea):
    cursor_pixel = Signal(int, int)
    edit_started = Signal()
    edit_point = Signal(int, int, bool)
    edit_rectangle = Signal(int, int, int, int, bool)
    edit_finished = Signal()
    nudge_requested = Signal(int, int)
    zoom_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(420, 520)
        self._image = None
        self._zoom: float | None = None
        self._grid = True
        self._drawing = False
        self._rect_start: QPoint | None = None
        self.edit_shape = "brush"
        self.horizontalScrollBar().valueChanged.connect(self.viewport().update)
        self.verticalScrollBar().valueChanged.connect(self.viewport().update)

    def set_image(self, image: Image.Image) -> None:
        self._image = pil_to_qimage(image)
        self._update_scrollbars()
        self.viewport().update()

    def set_pixel_grid(self, enabled: bool) -> None:
        self._grid = enabled
        self.viewport().update()

    def set_zoom_fit(self) -> None:
        self._zoom = None
        self._update_scrollbars()
        self.zoom_changed.emit("Fit")

    def set_zoom(self, scale: float) -> None:
        self._zoom = max(0.05, min(32.0, float(scale)))
        self._update_scrollbars()
        self.zoom_changed.emit(f"{round(self._zoom * 100)}%")

    def zoom_in(self) -> None:
        self.set_zoom(min(32.0, self.effective_zoom() * 2))

    def zoom_out(self) -> None:
        self.set_zoom(max(0.05, self.effective_zoom() / 2))

    def effective_zoom(self) -> float:
        if self._zoom is not None:
            return self._zoom
        if self._image is None:
            return 1.0
        return max(0.05, min((self.viewport().width() - 24) / self._image.width(), (self.viewport().height() - 24) / self._image.height()))

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self.viewport())
        painter.fillRect(self.viewport().rect(), QColor("#10151d"))
        if self._image is None:
            painter.setPen(QColor("#9ba9ba"))
            painter.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter, "Create or open a Builder project")
            return
        rect = self._draw_rect()
        self._checker(painter, rect)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(rect, self._image)
        painter.setPen(QColor("#52657c"))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        if self._grid and self.effective_zoom() >= 8:
            painter.save()
            painter.setClipRect(rect)
            painter.setPen(QPen(QColor(255, 255, 255, 55), 1))
            zoom = self.effective_zoom()
            for x in range(self._image.width() + 1):
                px = rect.left() + x * zoom
                painter.drawLine(QPointF(px, rect.top()), QPointF(px, rect.bottom()))
            for y in range(self._image.height() + 1):
                py = rect.top() + y * zoom
                painter.drawLine(QPointF(rect.left(), py), QPointF(rect.right(), py))
            painter.restore()
        if self._rect_start is not None and self._drawing:
            current = self.mapFromGlobal(self.cursor().pos())
            painter.setPen(QPen(QColor("#5fd7ff"), 1, Qt.PenStyle.DashLine))
            painter.drawRect(QRectF(QPointF(self._rect_start), QPointF(current)).normalized())

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        native = self._native(event.position())
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton) and native:
            self._drawing = True
            self.edit_started.emit()
            if self.edit_shape in {"rectangle", "ellipse"}:
                self._rect_start = event.position().toPoint()
            else:
                self.edit_point.emit(native.x(), native.y(), event.button() == Qt.MouseButton.RightButton)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        native = self._native(event.position())
        if native:
            self.cursor_pixel.emit(native.x(), native.y())
            if self._drawing and self.edit_shape not in {"rectangle", "ellipse"}:
                self.edit_point.emit(native.x(), native.y(), bool(event.buttons() & Qt.MouseButton.RightButton))
        self.viewport().update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drawing and event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            if self._rect_start is not None:
                first = self._native(QPointF(self._rect_start), clamp=False)
                second = self._native(event.position(), clamp=False)
                if first and second:
                    self.edit_rectangle.emit(first.x(), first.y(), second.x(), second.y(), event.button() == Qt.MouseButton.RightButton)
            self._drawing = False
            self._rect_start = None
            self.edit_finished.emit()
            self.viewport().update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        delta = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        mapping = {
            Qt.Key.Key_Left: (-delta, 0), Qt.Key.Key_Right: (delta, 0),
            Qt.Key.Key_Up: (0, -delta), Qt.Key.Key_Down: (0, delta),
        }
        if event.key() in mapping:
            self.nudge_requested.emit(*mapping[event.key()])
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_scrollbars()

    def _native(self, point: QPointF, clamp: bool = True) -> QPoint | None:
        if self._image is None:
            return None
        rect = self._draw_rect()
        if clamp and not rect.contains(point):
            return None
        zoom = self.effective_zoom()
        x, y = math.floor((point.x() - rect.left()) / zoom), math.floor((point.y() - rect.top()) / zoom)
        return QPoint(max(0, min(self._image.width() - 1, x)), max(0, min(self._image.height() - 1, y)))

    def _draw_rect(self) -> QRectF:
        if self._image is None:
            return QRectF()
        zoom = self.effective_zoom()
        width, height = self._image.width() * zoom, self._image.height() * zoom
        left = (self.viewport().width() - width) / 2 if width <= self.viewport().width() else -self.horizontalScrollBar().value()
        top = (self.viewport().height() - height) / 2 if height <= self.viewport().height() else -self.verticalScrollBar().value()
        return QRectF(left, top, width, height)

    def _update_scrollbars(self) -> None:
        if self._image is None:
            return
        zoom = self.effective_zoom()
        width, height = round(self._image.width() * zoom), round(self._image.height() * zoom)
        self.horizontalScrollBar().setRange(0, max(0, width - self.viewport().width()))
        self.verticalScrollBar().setRange(0, max(0, height - self.viewport().height()))
        self.viewport().update()

    @staticmethod
    def _checker(painter: QPainter, rect: QRectF) -> None:
        painter.save()
        painter.setClipRect(rect)
        tile = 12
        for y in range(math.floor(rect.top()), math.ceil(rect.bottom()), tile):
            for x in range(math.floor(rect.left()), math.ceil(rect.right()), tile):
                color = QColor("#d9dde2") if ((x // tile) + (y // tile)) & 1 else QColor("#aeb6c0")
                painter.fillRect(x, y, tile, tile, color)
        painter.restore()
