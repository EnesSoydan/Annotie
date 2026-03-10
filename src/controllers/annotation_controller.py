"""Etiket CRUD orchestrator - canvas ile model arasindaki kopru."""

from PySide6.QtGui import QUndoStack
from PySide6.QtCore import QTimer, QObject, Signal

from src.models.annotation import (
    BBoxAnnotation, PolygonAnnotation, OBBAnnotation,
    KeypointsAnnotation, ClassificationAnnotation, AnnotationType
)
from src.canvas.items.bbox_item import BBoxItem
from src.canvas.items.polygon_item import PolygonItem
from src.canvas.items.obb_item import OBBItem
from src.canvas.items.keypoint_item import KeypointItem
from src.commands.add_annotation_cmd import AddAnnotationCommand
from src.commands.delete_annotation_cmd import DeleteAnnotationCommand
from src.commands.change_class_cmd import ChangeClassCommand
from src.utils.geometry import rect_to_center_wh, normalize_bbox, normalize_points
from src.utils.constants import INSTANT_SAVE_DEBOUNCE_MS


class AnnotationController(QObject):
    """Tum etiket CRUD islemlerini yonetir."""

    annotation_created = Signal(object, object)   # (image, annotation)
    annotation_deleted = Signal(object, object)
    annotation_modified = Signal(object, object)
    annotations_loaded = Signal(object)           # image

    def __init__(self, canvas_scene, label_writer_fn, parent=None):
        super().__init__(parent)
        self.scene = canvas_scene
        self._label_writer_fn = label_writer_fn
        self._undo_stack = QUndoStack(self)
        self._current_image = None
        self._dataset = None
        self._active_class_id = 0
        self._annotation_list_panel = None
        self._class_list_panel = None

        # Anlik kaydetme debounce timer
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._flush_save)
        self._pending_save_image = None

        # Item -> annotation eslemesi
        self._item_to_ann = {}   # canvas_item -> annotation
        self._ann_to_item = {}   # annotation.uid -> canvas_item

    def set_dataset(self, dataset):
        self._dataset = dataset

    def set_current_image(self, image_item):
        """Gorsel degistiginde annotationlari canvas'a yukler."""
        self._current_image = image_item
        self._undo_stack.clear()
        self.scene.clear_annotations()
        self._item_to_ann.clear()
        self._ann_to_item.clear()

        if image_item is None:
            return

        image_item.load_dimensions()
        img_w = image_item.width
        img_h = image_item.height

        for ann in image_item.annotations:
            item = self._create_canvas_item(ann, img_w, img_h)
            if item:
                self.scene.add_annotation_item(item)
                self._item_to_ann[id(item)] = ann
                self._ann_to_item[ann.uid] = item
                item.signals.geometry_changed.connect(
                    lambda it: self._on_item_geometry_changed(it)
                )

        self.annotations_loaded.emit(image_item)
        self._notify_change()

    def _create_canvas_item(self, ann, img_w: int, img_h: int):
        """Bir annotation modelinden canvas item olusturur."""
        if self._dataset is None:
            return None

        cls = self._dataset.get_class_by_id(ann.class_id)
        class_name = cls.name if cls else f"Sinif {ann.class_id}"
        class_color = cls.color if cls else None

        from src.utils.colors import get_class_color
        if class_color is None:
            class_color = get_class_color(ann.class_id)

        ann_type = ann.ann_type

        if ann_type == AnnotationType.BBOX:
            return BBoxItem(ann, img_w, img_h, class_name, class_color)
        elif ann_type == AnnotationType.POLYGON:
            return PolygonItem(ann, img_w, img_h, class_name, class_color)
        elif ann_type == AnnotationType.OBB:
            return OBBItem(ann, img_w, img_h, class_name, class_color)
        elif ann_type == AnnotationType.KEYPOINTS:
            kp_names = []
            skeleton = []
            if cls and cls.keypoint_names:
                kp_names = cls.keypoint_names
                skeleton = cls.skeleton or []
            return KeypointItem(ann, img_w, img_h, class_name, class_color, kp_names, skeleton)
        return None

    # --- Etiket olusturma ---

    def create_bbox(self, rect):
        """BBox rect'inden (piksel QRectF) annotation olusturur."""
        if not self._current_image:
            return
        img = self._current_image
        img.load_dimensions()
        img_w, img_h = img.width, img.height

        cx = (rect.x() + rect.width() / 2) / img_w
        cy = (rect.y() + rect.height() / 2) / img_h
        w = rect.width() / img_w
        h = rect.height() / img_h

        ann = BBoxAnnotation(
            class_id=self._active_class_id,
            x_center=cx, y_center=cy, width=w, height=h
        )
        item = BBoxItem(ann, img_w, img_h,
                        self._get_class_name(ann.class_id),
                        self._get_class_color(ann.class_id))
        item.signals.geometry_changed.connect(lambda it: self._on_item_geometry_changed(it))
        self._execute_add(ann, item)

    def create_polygon(self, points_pixel):
        """Piksel koordinat listesinden polygon annotation olusturur."""
        if not self._current_image:
            return
        img = self._current_image
        img.load_dimensions()
        img_w, img_h = img.width, img.height

        norm_points = [(x / img_w, y / img_h) for x, y in points_pixel]
        ann = PolygonAnnotation(class_id=self._active_class_id, points=norm_points)
        item = PolygonItem(ann, img_w, img_h,
                           self._get_class_name(ann.class_id),
                           self._get_class_color(ann.class_id))
        item.signals.geometry_changed.connect(lambda it: self._on_item_geometry_changed(it))
        self._execute_add(ann, item)

    def create_obb(self, corners_pixel):
        """Piksel koordinat koselerinden OBB annotation olusturur."""
        if not self._current_image:
            return
        img = self._current_image
        img.load_dimensions()
        img_w, img_h = img.width, img.height

        norm_corners = [(x / img_w, y / img_h) for x, y in corners_pixel]
        ann = OBBAnnotation(class_id=self._active_class_id, corners=norm_corners)
        item = OBBItem(ann, img_w, img_h,
                       self._get_class_name(ann.class_id),
                       self._get_class_color(ann.class_id))
        item.signals.geometry_changed.connect(lambda it: self._on_item_geometry_changed(it))
        self._execute_add(ann, item)

    def create_keypoints(self, bbox_norm, keypoints):
        """Normalize bbox ve keypoint listesinden annotation olusturur."""
        if not self._current_image:
            return
        img = self._current_image
        img.load_dimensions()
        img_w, img_h = img.width, img.height

        ann = KeypointsAnnotation(
            class_id=self._active_class_id,
            x_center=bbox_norm[0], y_center=bbox_norm[1],
            width=bbox_norm[2], height=bbox_norm[3],
            keypoints=keypoints
        )
        cls = self._dataset.get_class_by_id(self._active_class_id) if self._dataset else None
        kp_names = cls.keypoint_names if cls else []
        skeleton = cls.skeleton if cls else []
        item = KeypointItem(ann, img_w, img_h,
                            self._get_class_name(ann.class_id),
                            self._get_class_color(ann.class_id),
                            kp_names, skeleton)
        item.signals.geometry_changed.connect(lambda it: self._on_item_geometry_changed(it))
        self._execute_add(ann, item)

    def create_classification(self, class_id: int):
        """Gorsel siniflandirma etiketi olusturur."""
        if not self._current_image:
            return
        # Onceki siniflandirmayi kaldir
        for ann in list(self._current_image.annotations):
            if ann.ann_type == AnnotationType.CLASSIFICATION:
                item = self._ann_to_item.get(ann.uid)
                self.delete_annotation_object(ann, item)

        ann = ClassificationAnnotation(class_id=class_id)
        self._current_image.annotations.append(ann)
        self._current_image.mark_dirty()
        self._schedule_save(self._current_image)
        self._notify_change()

    def _execute_add(self, annotation, canvas_item):
        """Undo/redo yiginina add komutu ekler."""
        cmd = AddAnnotationCommand(
            self._current_image, annotation, canvas_item, self
        )
        self._undo_stack.push(cmd)

    def _on_annotation_added(self, image, annotation, canvas_item):
        """AddAnnotationCommand.redo() tarafindan cagrilir."""
        image.annotations.append(annotation)
        self._item_to_ann[id(canvas_item)] = annotation
        self._ann_to_item[annotation.uid] = canvas_item
        image.mark_dirty()
        self._schedule_save(image)
        self.annotation_created.emit(image, annotation)
        self._notify_change()

    def _on_annotation_removed(self, image, annotation):
        """DeleteAnnotationCommand.redo() tarafindan cagrilir."""
        uid = annotation.uid
        canvas_item = self._ann_to_item.pop(uid, None)
        if canvas_item:
            self._item_to_ann.pop(id(canvas_item), None)
        image.mark_dirty()
        self._schedule_save(image)
        self.annotation_deleted.emit(image, annotation)
        self._notify_change()

    # --- Silme ---

    def delete_selected(self):
        """Canvas'ta secili annotation'i siler."""
        selected = self.scene.selectedItems()
        for item in selected:
            ann = self._item_to_ann.get(id(item))
            if ann and self._current_image:
                cmd = DeleteAnnotationCommand(
                    self._current_image, ann, item, self
                )
                self._undo_stack.push(cmd)

    def delete_annotation_object(self, annotation, canvas_item):
        if self._current_image and annotation in self._current_image.annotations:
            cmd = DeleteAnnotationCommand(
                self._current_image, annotation, canvas_item, self
            )
            self._undo_stack.push(cmd)

    # --- Sinif degistirme ---

    def change_annotation_class(self, annotation, canvas_item, new_class_id: int):
        if not self._current_image:
            return
        cmd = ChangeClassCommand(
            self._current_image, annotation, canvas_item,
            annotation.class_id, new_class_id, self
        )
        self._undo_stack.push(cmd)

    def _refresh_item_class(self, canvas_item, class_id: int):
        canvas_item.class_name = self._get_class_name(class_id)
        canvas_item.class_color = self._get_class_color(class_id)
        canvas_item.update_from_annotation()

    # --- Geometri degisikligi ---

    def _on_item_geometry_changed(self, canvas_item):
        if self._current_image:
            self._current_image.mark_dirty()
            self._schedule_save(self._current_image)
            ann = self._item_to_ann.get(id(canvas_item))
            if ann:
                self.annotation_modified.emit(self._current_image, ann)

    # --- Kaydetme ---

    def _schedule_save(self, image):
        """Debounce ile anlik kaydetme planlar."""
        self._pending_save_image = image
        self._save_timer.start(INSTANT_SAVE_DEBOUNCE_MS)

    def _flush_save(self):
        if self._pending_save_image:
            self._save_image(self._pending_save_image)
            self._pending_save_image = None

    def _save_image(self, image):
        """Bir gorselin etiketlerini aninda yazar."""
        if self._label_writer_fn:
            self._label_writer_fn(image)
        image.mark_clean()

    def _notify_change(self):
        """Annotation listesi panelini gunceller."""
        if self._annotation_list_panel and self._current_image:
            self._annotation_list_panel.load_annotations(
                self._current_image.annotations,
                self._dataset.classes if self._dataset else []
            )
        if self._current_image:
            count = len(self._current_image.annotations)
            # Pencere durum cubugundan etiket sayisi guncelle
            window = self._get_main_window()
            if window:
                window.update_annotation_count(count)

    def _get_main_window(self):
        try:
            from PySide6.QtWidgets import QApplication
            for w in QApplication.topLevelWidgets():
                if hasattr(w, 'update_annotation_count'):
                    return w
        except Exception:
            pass
        return None

    # --- Yardimci ---

    def _get_class_name(self, class_id: int) -> str:
        if self._dataset:
            cls = self._dataset.get_class_by_id(class_id)
            if cls:
                return cls.name
        return f"Sinif {class_id}"

    def _get_class_color(self, class_id: int):
        if self._dataset:
            cls = self._dataset.get_class_by_id(class_id)
            if cls and cls.color:
                return cls.color
        from src.utils.colors import get_class_color
        return get_class_color(class_id)

    def set_active_class(self, class_id: int):
        self._active_class_id = class_id

    def set_annotation_list_panel(self, panel):
        self._annotation_list_panel = panel

    def set_class_list_panel(self, panel):
        self._class_list_panel = panel

    @property
    def undo_stack(self) -> QUndoStack:
        return self._undo_stack
