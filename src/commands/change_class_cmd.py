"""Etiket sinifini degistirme geri alinanabilir komutu."""

from PySide6.QtGui import QUndoCommand


class ChangeClassCommand(QUndoCommand):
    def __init__(self, image_item, annotation, canvas_item,
                 old_class_id, new_class_id, annotation_controller):
        super().__init__("Sinif Degistir")
        self._image = image_item
        self._annotation = annotation
        self._canvas_item = canvas_item
        self._old_id = old_class_id
        self._new_id = new_class_id
        self._ctrl = annotation_controller

    def redo(self):
        self._annotation.class_id = self._new_id
        self._ctrl._refresh_item_class(self._canvas_item, self._new_id)
        self._ctrl._save_image(self._image)
        self._ctrl._notify_change()

    def undo(self):
        self._annotation.class_id = self._old_id
        self._ctrl._refresh_item_class(self._canvas_item, self._old_id)
        self._ctrl._save_image(self._image)
        self._ctrl._notify_change()
