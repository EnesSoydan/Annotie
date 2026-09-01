"""BBox dolgu stili ve piksel alan rozeti."""

from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter
from PySide6.QtWidgets import QGraphicsItem

from src.utils.bbox_metrics import format_pixel_dimensions


BBOX_FILL_ALPHA = 72


def bbox_fill_color(color: QColor) -> QColor:
    """Sınıf renginden CVAT benzeri yarı saydam bbox dolgusu üretir."""
    fill = QColor(color)
    fill.setAlpha(BBOX_FILL_ALPHA)
    return fill


class PixelSizeBadge(QGraphicsItem):
    """BBox içine sığan dinamik genişlik/yükseklik etiketi."""

    _H_PADDING = 4.0
    _V_PADDING = 1.5
    _SCREEN_GAP = 3.0
    _TARGET_BOX_WIDTH_RATIO = 0.60

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._font = QFont("Segoe UI", 6, QFont.Weight.DemiBold)
        self._text = ""
        self._bounds = QRectF()
        self._box_rect = QRectF()
        self._view_zoom = 1.0

        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(False)
        self.setZValue(6)

    def set_color(self, color: QColor):
        self._color = QColor(color)
        self.update()

    def set_dimensions(self, width: float, height: float):
        text = format_pixel_dimensions(width, height)
        if text == self._text:
            return

        self.prepareGeometryChange()
        self._text = text
        metrics = QFontMetricsF(self._font)
        text_rect = metrics.boundingRect(text)
        self._bounds = QRectF(
            0.0,
            0.0,
            math.ceil(text_rect.width()) + self._H_PADDING * 2,
            math.ceil(text_rect.height()) + self._V_PADDING * 2,
        )
        self._update_layout()
        self.update()

    def set_box_rect(self, rect: QRectF):
        self._box_rect = QRectF(rect).normalized()
        self._update_layout()

    def set_view_zoom(self, zoom: float):
        self._view_zoom = max(0.01, float(zoom))
        self._update_layout()

    def _update_layout(self):
        if self._bounds.isEmpty() or self._box_rect.isEmpty():
            self.setVisible(False)
            return

        zoom_cap = max(1.0, self._view_zoom)
        gap = self._SCREEN_GAP / zoom_cap
        available_width = self._box_rect.width() - gap * 2
        available_height = self._box_rect.height() - gap * 2
        if available_width <= 0.0 or available_height <= 0.0:
            self.setVisible(False)
            return

        target_width = min(
            self._box_rect.width() * self._TARGET_BOX_WIDTH_RATIO,
            available_width,
        )
        # Rozet normal koşullarda bbox genişliğinin %60'ını kaplar. Çok basık
        # kutularda üst-alt sınırın dışına taşmaması için yükseklik belirleyicidir.
        scale = min(
            target_width / self._bounds.width(),
            available_height / self._bounds.height(),
        )

        self.setScale(scale)
        self.setPos(self._box_rect.left() + gap, self._box_rect.top() + gap)
        self.setVisible(scale > 0.0)

    @property
    def text(self) -> str:
        return self._text

    def boundingRect(self) -> QRectF:
        return self._bounds.adjusted(-1.0, -1.0, 1.0, 1.0)

    def paint(self, painter: QPainter, option, widget=None):
        if not self._text:
            return

        background = QColor(self._color)
        background.setAlpha(220)
        luminance = (
            0.299 * background.red()
            + 0.587 * background.green()
            + 0.114 * background.blue()
        )
        foreground = (
            QColor(20, 20, 20)
            if luminance > 160
            else QColor(255, 255, 255)
        )

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(self._bounds, 2.5, 2.5)

        painter.setFont(self._font)
        painter.setPen(foreground)
        text_rect = self._bounds.adjusted(
            self._H_PADDING, 0.0, -self._H_PADDING, 0.0
        )
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._text,
        )
