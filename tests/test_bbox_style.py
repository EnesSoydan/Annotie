"""BBox alan hesaplama, stil ve dinamik rozet testleri."""

import os
import unittest

from src.utils.bbox_metrics import format_pixel_dimensions

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QApplication, QGraphicsView

    from src.canvas.canvas_scene import CanvasScene
    from src.canvas.canvas_view import CanvasView
    from src.canvas.items.bbox_item import BBoxItem
    from src.canvas.items.bbox_style import BBOX_FILL_ALPHA, bbox_fill_color
    from src.canvas.tools.bbox_tool import BBoxTool
    from src.models.annotation import BBoxAnnotation

    HAS_QT = True
    QT_SKIP_REASON = ""
except ModuleNotFoundError as exc:
    HAS_QT = False
    QT_SKIP_REASON = f"Qt bbox test dependencies are unavailable: {exc}"


class BBoxStyleTests(unittest.TestCase):
    def test_formats_dimensions_with_one_decimal_place(self):
        self.assertEqual(
            format_pixel_dimensions(342.46, 256.12),
            "342.5 x 256.1 px",
        )

    def test_negative_dimensions_are_clamped_to_zero(self):
        self.assertEqual(format_pixel_dimensions(-10, 4), "0.0 x 4.0 px")


@unittest.skipUnless(HAS_QT, QT_SKIP_REASON)
class BBoxQtStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_fill_keeps_class_rgb_and_applies_bbox_alpha(self):
        source = QColor(12, 34, 56, 255)

        fill = bbox_fill_color(source)

        self.assertEqual((fill.red(), fill.green(), fill.blue()), (12, 34, 56))
        self.assertEqual(fill.alpha(), BBOX_FILL_ALPHA)
        self.assertEqual(source.alpha(), 255)

    def test_size_badge_updates_during_handle_resize(self):
        annotation = BBoxAnnotation(
            class_id=0,
            x_center=0.5,
            y_center=0.5,
            width=0.2,
            height=0.4,
        )
        item = BBoxItem(annotation, 200, 100, "car", QColor("#22aa44"))
        self.assertEqual(item._size_badge.text, "40.0 x 40.0 px")

        item.handle_moved(2, 150.0, 80.0)

        self.assertEqual(item._size_badge.text, "70.0 x 50.0 px")

    def test_size_badge_uses_sixty_percent_width_and_three_pixel_gap(self):
        annotation = BBoxAnnotation(
            class_id=0,
            x_center=0.5,
            y_center=0.5,
            width=0.5,
            height=0.6,
        )
        item = BBoxItem(annotation, 200, 100, "car", QColor("#22aa44"))

        item.set_view_zoom(2.0)
        badge = item._size_badge
        rect = item.rect().normalized()
        screen_gap = (badge.pos().x() - rect.left()) * 2.0
        badge_width_ratio = badge._bounds.width() * badge.scale() / rect.width()

        self.assertTrue(badge.isVisible())
        self.assertAlmostEqual(screen_gap, 3.0)
        self.assertAlmostEqual(badge_width_ratio, 0.60, places=2)

    def test_handles_shrink_at_high_zoom(self):
        annotation = BBoxAnnotation(
            class_id=0,
            x_center=0.5,
            y_center=0.5,
            width=0.5,
            height=0.6,
        )
        item = BBoxItem(annotation, 200, 100, "car", QColor("#22aa44"))

        item.set_view_zoom(1.0)
        self.assertEqual(item._handles[0].display_size, 7.0)

        item.set_view_zoom(9.0)
        self.assertEqual(item._handles[0].display_size, 4.0)
        self.assertEqual(item._handles[0].rect().width(), 4.0)

    def test_canvas_view_propagates_zoom_to_existing_items(self):
        scene = CanvasScene()
        view = CanvasView(scene)
        scene.set_image(QPixmap(200, 100))
        annotation = BBoxAnnotation(
            class_id=0,
            x_center=0.5,
            y_center=0.5,
            width=0.5,
            height=0.6,
        )
        item = BBoxItem(annotation, 200, 100, "car", QColor("#22aa44"))
        scene.add_annotation_item(item)

        view._apply_zoom(9.0)

        self.assertEqual(item._handles[0].display_size, 4.0)
        self.assertEqual(item._size_badge._view_zoom, 9.0)

    def test_preview_uses_active_class_fill_and_updates_dimensions(self):
        class ControllerStub:
            @staticmethod
            def get_active_class_color():
                return QColor("#3366cc")

        class LeftClickStub:
            @staticmethod
            def button():
                return Qt.MouseButton.LeftButton

        scene = CanvasScene()
        scene.set_image(QPixmap(200, 100))
        tool = BBoxTool(QGraphicsView(scene), scene, ControllerStub())

        tool.mouse_press(LeftClickStub(), QPointF(10.0, 10.0))
        tool.mouse_move(None, QPointF(40.5, 30.25))

        fill = tool._preview.brush().color()
        self.assertEqual((fill.red(), fill.green(), fill.blue()), (51, 102, 204))
        self.assertEqual(fill.alpha(), BBOX_FILL_ALPHA)
        self.assertEqual(tool._size_badge.text, "30.5 x 20.2 px")

        tool.set_view_zoom(4.0)
        screen_gap = (tool._size_badge.pos().x() - tool._preview.rect().left()) * 4.0
        self.assertAlmostEqual(screen_gap, 3.0)


if __name__ == "__main__":
    unittest.main()
