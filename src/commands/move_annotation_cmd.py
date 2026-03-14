"""Etiket tasima / yeniden boyutlandirma geri alinabilir komutu."""

from PySide6.QtGui import QUndoCommand
from src.models.annotation import AnnotationType


class MoveAnnotationCommand(QUndoCommand):
    """Bir etiketi tasima veya handle ile boyutlandirma islemi icin undo/redo komutu."""

    def __init__(self, image, annotation, canvas_item, old_state: dict, new_state: dict,
                 annotation_controller):
        super().__init__("Etiket Taşı")
        self._image = image
        self._annotation = annotation
        self._canvas_item = canvas_item
        self._old_state = old_state
        self._new_state = new_state
        self._ctrl = annotation_controller

    def undo(self):
        self._apply_state(self._old_state)

    def redo(self):
        self._apply_state(self._new_state)

    def _apply_state(self, state: dict):
        """State sozlugundeki alanlari annotation'a uygular ve item'i gunceller."""
        ann = self._annotation
        ann_type = ann.ann_type

        if ann_type == AnnotationType.BBOX:
            ann.x_center = state['x_center']
            ann.y_center = state['y_center']
            ann.width    = state['width']
            ann.height   = state['height']
        elif ann_type == AnnotationType.OBB:
            ann.corners = [tuple(c) for c in state['corners']]
        elif ann_type == AnnotationType.POLYGON:
            ann.points = [tuple(p) for p in state['points']]
        elif ann_type == AnnotationType.KEYPOINTS:
            ann.keypoints = [list(kp) for kp in state['keypoints']]

        # update_from_annotation() kendi içinde setPos(0,0) yapıyor (flag korumalı)
        self._canvas_item.update_from_annotation()

        # Kaydetmeyi planla
        self._image.mark_dirty()
        self._ctrl._schedule_save(self._image)
