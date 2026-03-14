"""Etiket silme geri alinanabilir komutu."""

from PySide6.QtGui import QUndoCommand


class DeleteAnnotationCommand(QUndoCommand):
    def __init__(self, image_item, annotation, canvas_item, annotation_controller):
        super().__init__("Etiket Sil")
        self._image = image_item
        self._annotation = annotation
        self._canvas_item = canvas_item
        self._ctrl = annotation_controller

    def redo(self):
        if self._annotation in self._image.annotations:
            self._image.annotations.remove(self._annotation)
        self._ctrl.scene.remove_annotation_item(self._canvas_item)
        self._ctrl._on_annotation_removed(self._image, self._annotation)

    def undo(self):
        # NOT: _on_annotation_added zaten image.annotations.append() yapıyor;
        # burada tekrar append etmek ghost etiket oluşturuyordu.
        self._ctrl.scene.add_annotation_item(self._canvas_item)
        self._ctrl._on_annotation_added(self._image, self._annotation, self._canvas_item)
