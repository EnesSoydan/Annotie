"""QGraphicsView: zoom, pan ve arac yonlendirme."""

from PySide6.QtWidgets import QGraphicsView, QGraphicsPixmapItem, QGraphicsTextItem
from PySide6.QtCore import Qt, Signal, QPointF, QEvent
from PySide6.QtGui import QPainter, QMouseEvent, QWheelEvent, QKeyEvent, QColor, QPen
from src.canvas.canvas_scene import CanvasScene
from src.utils.constants import ZOOM_IN_FACTOR, ZOOM_OUT_FACTOR, MIN_ZOOM, MAX_ZOOM


class CanvasView(QGraphicsView):
    """Ana canvas gorunumu - zoom, pan ve arac destegi."""

    mouse_scene_pos_changed = Signal(float, float)
    zoom_changed = Signal(float)
    # Bir annotation item'ina sag tik yapildiginda emit edilir: (item, global_pos)
    context_menu_requested = Signal(object, object)
    # Eski hover silme sinyali; geriye uyumluluk icin tutuluyor.
    delete_hovered_item_requested = Signal(object)
    delete_image_requested = Signal()

    # Fare sÃ¼rÃ¼kleme eÅŸiÄŸi (viewport piksel): bu kadar hareket â†’ pan; daha az â†’ tÄ±klama
    _DRAG_PAN_THRESHOLD = 5

    def __init__(self, scene: CanvasScene, parent=None):
        super().__init__(scene, parent)
        self._scene = scene
        self._active_tool = None
        self._panning = False
        self._pan_start = QPointF()
        self._zoom_level = 1.0
        self._show_crosshair = True
        self._crosshair_pos = None
        # Cizim araclari icin bekleyen tiklama (drag mi, click mi tespiti)
        self._pending_click_pos = None        # viewport pos
        self._pending_click_scene_pos = None  # scene pos
        self._hovered_annotation_item = None  # Mouse altÄ±ndaki annotation item (hover)

        # Render ayarlari
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setBackgroundBrush(QColor("#2b2b2b"))
        self.setMouseTracking(True)
        # Viewport'ta da mouse tracking aÃ§Ä±k olmalÄ±, yoksa buton basÄ±lÄ±
        # olmadan mouseMoveEvent tetiklenmez
        self.viewport().setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Viewport event'lerini yakala: Enter â†’ focus al, Del â†’ hover sil
        self.viewport().installEventFilter(self)

    def set_tool(self, tool):
        """Aktif araci degistirir."""
        if self._active_tool:
            self._active_tool.deactivate()
        self._active_tool = tool
        if tool:
            tool.activate()
            if hasattr(tool, "set_view_zoom"):
                tool.set_view_zoom(self._zoom_level)
            cursor = tool.get_cursor()
            if cursor:
                self.setCursor(cursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)

    def get_tool(self):
        return self._active_tool

    # --- Zoom ---
    def zoom_in(self):
        self._apply_zoom(ZOOM_IN_FACTOR)

    def zoom_out(self):
        self._apply_zoom(ZOOM_OUT_FACTOR)

    def zoom_fit(self):
        """Gorseli pencereye sigdir."""
        if self._scene.has_image:
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self._zoom_level = self.transform().m11()
            self._sync_overlay_zoom()
            self.zoom_changed.emit(self._zoom_level)

    def zoom_100(self):
        """%100 zoom."""
        self.resetTransform()
        self._zoom_level = 1.0
        self._sync_overlay_zoom()
        self.zoom_changed.emit(self._zoom_level)

    def _apply_zoom(self, factor: float):
        new_zoom = self._zoom_level * factor
        if MIN_ZOOM <= new_zoom <= MAX_ZOOM:
            self.scale(factor, factor)
            self._zoom_level = new_zoom
            self._sync_overlay_zoom()
            self.zoom_changed.emit(self._zoom_level)

    def _sync_overlay_zoom(self):
        """Annotation rozetlerini ve tutamaçlarını görünüm zoom'una uyarlar."""
        for item in self._scene.get_annotation_items():
            if hasattr(item, "set_view_zoom"):
                item.set_view_zoom(self._zoom_level)
        if self._active_tool and hasattr(self._active_tool, "set_view_zoom"):
            self._active_tool.set_view_zoom(self._zoom_level)

    # --- Yardimci ---
    def _has_interactive_item_at(self, scene_pos) -> bool:
        """Verilen sahne konumunda tiklanabilir annotation item var mi kontrol eder.

        Arkaplan pixmap ve etiket metinleri (mouse'u kabul etmeyen) sayilmaz.
        """
        for item in self.scene().items(scene_pos):
            # Arkaplan ve etiket metinleri â†’ atla
            if isinstance(item, (QGraphicsPixmapItem, QGraphicsTextItem)):
                continue
            # Mouse tuslarini kabul etmeyen item â†’ atla
            if item.acceptedMouseButtons() == Qt.MouseButton.NoButton:
                continue
            return True
        return False

    # --- Olaylar ---
    def wheelEvent(self, event: QWheelEvent):
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        event.accept()

    def contextMenuEvent(self, event):
        """SaÄŸ tÄ±k: annotation item varsa context_menu_requested sinyali gÃ¶nder."""
        scene_pos = self.mapToScene(event.pos())
        items = self.scene().items(scene_pos)
        for item in items:
            if hasattr(item, '_annotation') and item._annotation is not None:
                self.context_menu_requested.emit(item, event.globalPos())
                event.accept()
                return
        event.ignore()

    def mousePressEvent(self, event: QMouseEvent):
        # Orta tuÅŸ â†’ her zaman pan
        if event.button() == Qt.MouseButton.MiddleButton:
            self._start_pan(event)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())

            if self._active_tool:
                if getattr(self._active_tool, 'use_qt_selection', False):
                    # SelectTool: item'e tik â†’ Qt seÃ§im
                    # BoÅŸ alana tik â†’ bekle (click=deselect / drag=pan; eÅŸik moveMoveEvent'te)
                    if self._has_interactive_item_at(scene_pos):
                        super().mousePressEvent(event)
                    else:
                        self._pending_click_pos = event.pos()
                        self._pending_click_scene_pos = scene_pos
                    return
                # Cizim araclari: hemen tetikleme, once drag/click tespiti bekle
                self._pending_click_pos = event.pos()
                self._pending_click_scene_pos = scene_pos
                return

        super().mousePressEvent(event)

    def eventFilter(self, obj, event):
        """Viewport event'lerini yakala: focus + hover Del."""
        if obj is self.viewport():
            t = event.type()
            if t == QEvent.Type.Enter:
                # Mouse viewport'a girdiÄŸinde klavye odaÄŸÄ±nÄ± al
                self.viewport().setFocus(Qt.FocusReason.OtherFocusReason)
            elif t == QEvent.Type.KeyPress:
                ke = event
                if ke.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                    self.delete_image_requested.emit()
                    ke.accept()
                    return True
        return super().eventFilter(obj, event)

    def mouseMoveEvent(self, event: QMouseEvent):
        scene_pos = self.mapToScene(event.pos())
        self.mouse_scene_pos_changed.emit(scene_pos.x(), scene_pos.y())
        self._crosshair_pos = event.pos()
        # Hover altÄ±ndaki annotation item'Ä± takip et (seÃ§meden Del iÃ§in)
        self._update_hovered_item(scene_pos)

        if self._panning:
            self._do_pan(event)
            return

        # Bekleyen tiklama varsa: drag mÄ± click mÄ± kontrol et
        if self._pending_click_pos is not None and \
                (event.buttons() & Qt.MouseButton.LeftButton):
            delta = (event.pos() - self._pending_click_pos).manhattanLength()
            if delta > self._DRAG_PAN_THRESHOLD:
                # Drag tespit edildi â†’ pan moduna gec, tiklama iptal
                self._pending_click_pos = None
                self._pending_click_scene_pos = None
                self._start_pan(event)
                return
            # Esik asilmadi: araca mouse_move gonder (onizleme icin)
            if self._active_tool:
                self._active_tool.mouse_move(event, scene_pos)
            if self._show_crosshair:
                self.viewport().update()
            return

        if self._active_tool:
            if getattr(self._active_tool, 'use_qt_selection', False):
                super().mouseMoveEvent(event)
            else:
                self._active_tool.mouse_move(event, scene_pos)
                super().mouseMoveEvent(event)
        else:
            super().mouseMoveEvent(event)

        if self._show_crosshair:
            self.viewport().update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        # Orta tuÅŸ veya sol tuÅŸ pan bitti
        if self._panning and event.button() in (
            Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton
        ):
            self._end_pan()
            return

        # Bekleyen tiklama: drag olmadi â†’ click olarak isle
        if self._pending_click_pos is not None and \
                event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self._pending_click_scene_pos
            self._pending_click_pos = None
            self._pending_click_scene_pos = None
            if self._active_tool and getattr(self._active_tool, 'use_qt_selection', False):
                # SelectTool: boÅŸ alana tÄ±k â†’ seÃ§imi kaldÄ±r
                self._scene.clearSelection()
            elif self._active_tool:
                self._active_tool.mouse_press(event, scene_pos)
                self._active_tool.mouse_release(event, scene_pos)
            return

        scene_pos = self.mapToScene(event.pos())

        if self._active_tool and event.button() == Qt.MouseButton.LeftButton:
            if getattr(self._active_tool, 'use_qt_selection', False):
                super().mouseReleaseEvent(event)
                return
            self._active_tool.mouse_release(event, scene_pos)
            return

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        scene_pos = self.mapToScene(event.pos())
        if self._active_tool:
            if getattr(self._active_tool, 'use_qt_selection', False):
                super().mouseDoubleClickEvent(event)
                return
            self._active_tool.mouse_double_click(event, scene_pos)
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.setCursor(Qt.CursorShape.OpenHandCursor)

        # Del/Backspace: o anda yuklu olan gorseli sil.
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_image_requested.emit()
            event.accept()
            return

        if self._active_tool:
            self._active_tool.key_press(event)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if self._active_tool:
                cursor = self._active_tool.get_cursor()
                self.setCursor(cursor if cursor else Qt.CursorShape.CrossCursor)
        super().keyReleaseEvent(event)

    # --- Hover item takibi ---
    def _update_hovered_item(self, scene_pos):
        """Mouse altÄ±ndaki annotation item'Ä± gÃ¼nceller (seÃ§meden Del iÃ§in)."""
        found = None
        for item in self.scene().items(scene_pos):
            if isinstance(item, (QGraphicsPixmapItem, QGraphicsTextItem)):
                continue
            if item.acceptedMouseButtons() == Qt.MouseButton.NoButton:
                continue
            if hasattr(item, '_annotation') and item._annotation is not None:
                found = item
                break
        self._hovered_annotation_item = found

    # --- Pan ---
    def _start_pan(self, event):
        self._panning = True
        self._pan_start = event.pos()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _do_pan(self, event):
        delta = event.pos() - self._pan_start
        self._pan_start = event.pos()
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() - int(delta.x())
        )
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - int(delta.y())
        )

    def _end_pan(self):
        self._panning = False
        if self._active_tool:
            cursor = self._active_tool.get_cursor()
            self.setCursor(cursor if cursor else Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    # --- Crosshair ---
    def set_show_crosshair(self, show: bool):
        self._show_crosshair = show
        self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._show_crosshair and self._crosshair_pos and self._scene.has_image:
            painter = QPainter(self.viewport())
            painter.setPen(QPen(QColor(255, 255, 255, 80), 1, Qt.PenStyle.DashLine))
            pos = self._crosshair_pos
            vw = self.viewport().width()
            vh = self.viewport().height()
            painter.drawLine(0, int(pos.y()), vw, int(pos.y()))
            painter.drawLine(int(pos.x()), 0, int(pos.x()), vh)
            painter.end()
