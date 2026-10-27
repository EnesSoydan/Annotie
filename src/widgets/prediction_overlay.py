"""Onizleme icin hafif (duzenlenemez) annotation cizimi."""

from __future__ import annotations

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsPathItem, QGraphicsScene, QGraphicsSimpleTextItem,
    QGraphicsRectItem,
)

from src.models.annotation import AnnotationType


def annotation_path(ann, w: int, h: int) -> QPainterPath:
    path = QPainterPath()
    t = ann.ann_type
    if t in (AnnotationType.BBOX, AnnotationType.KEYPOINTS):
        path.addRect(QRectF((ann.x_center - ann.width / 2) * w,
                            (ann.y_center - ann.height / 2) * h,
                            ann.width * w, ann.height * h))
        if t == AnnotationType.KEYPOINTS:
            for x, y, v in ann.keypoints:
                if v > 0:
                    path.addEllipse(QPointF(x * w, y * h), 3, 3)
    elif t in (AnnotationType.POLYGON, AnnotationType.OBB):
        pts = ann.points if t == AnnotationType.POLYGON else ann.corners
        if pts:
            path.moveTo(pts[0][0] * w, pts[0][1] * h)
            for x, y in pts[1:]:
                path.lineTo(x * w, y * h)
            path.closeSubpath()
    return path


def label_anchor(ann, w: int, h: int) -> QPointF:
    t = ann.ann_type
    if t in (AnnotationType.BBOX, AnnotationType.KEYPOINTS):
        return QPointF((ann.x_center - ann.width / 2) * w, (ann.y_center - ann.height / 2) * h)
    pts = getattr(ann, "points", None) or getattr(ann, "corners", None) or [(0, 0)]
    x, y = min(pts, key=lambda p: (p[1], p[0]))
    return QPointF(x * w, y * h)


def add_annotation(scene: QGraphicsScene, ann, w: int, h: int, color: QColor,
                   text: str = "", dashed: bool = False, fill: bool = False,
                   width: float = 2.0):
    """Annotation'i sahneye ekler. Siniflandirma etiketleri sol uste yazi olarak cizilir."""
    if ann.ann_type == AnnotationType.CLASSIFICATION:
        _add_text(scene, QPointF(4, 4), text, color, ignore_y_offset=True)
        return
    pen = QPen(color, width)
    pen.setCosmetic(True)
    if dashed:
        pen.setStyle(Qt.PenStyle.DashLine)
    item = QGraphicsPathItem(annotation_path(ann, w, h))
    item.setPen(pen)
    if fill:
        c = QColor(color)
        c.setAlpha(45)
        item.setBrush(QBrush(c))
    scene.addItem(item)
    if text:
        _add_text(scene, label_anchor(ann, w, h), text, color)


def _add_text(scene, pos: QPointF, text: str, color: QColor, ignore_y_offset=False):
    bg = QGraphicsRectItem()
    bg.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
    label = QGraphicsSimpleTextItem(text, bg)
    label.setBrush(QBrush(QColor("white") if color.lightness() < 150 else QColor("black")))
    r = label.boundingRect().adjusted(-3, -1, 3, 1)
    bg.setRect(r)
    bg.setBrush(QBrush(color))
    bg.setPen(QPen(Qt.PenStyle.NoPen))
    bg.setPos(pos)
    if not ignore_y_offset:
        label.setPos(0, -r.height())
        bg.setRect(r.translated(0, -r.height()))
    scene.addItem(bg)
