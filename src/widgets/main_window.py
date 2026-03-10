"""Ana pencere: menuler, toolbar, dock paneller, durum cubugu."""

from PySide6.QtWidgets import (
    QMainWindow, QStatusBar, QDockWidget, QFileDialog,
    QMessageBox, QLabel, QWidget, QMenu
)
from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QAction, QKeySequence, QShortcut

from src.canvas.canvas_scene import CanvasScene
from src.canvas.canvas_view import CanvasView
from src.canvas.tools.select_tool import SelectTool
from src.canvas.tools.bbox_tool import BBoxTool
from src.canvas.tools.polygon_tool import PolygonTool
from src.canvas.tools.obb_tool import OBBTool
from src.canvas.tools.keypoint_tool import KeypointTool
from src.canvas.tools.classify_tool import ClassifyTool

from src.widgets.toolbar import MainToolbar
from src.widgets.image_list_panel import ImageListPanel
from src.widgets.class_list_panel import ClassListPanel
from src.widgets.annotation_list_panel import AnnotationListPanel
from src.widgets.properties_panel import PropertiesPanel
from src.widgets.settings_dialog import SettingsDialog
from src.widgets.new_dataset_dialog import NewDatasetDialog
from src.widgets.export_dialog import ExportDialog
from src.widgets.import_dialog import ImportDialog

from src.controllers.annotation_controller import AnnotationController
from src.controllers.dataset_controller import DatasetController
from src.controllers.autosave_controller import AutosaveController
from src.io.dataset_exporter import export_dataset, create_dataset_structure
from src.utils.config import AppConfig
from src.utils.constants import APP_NAME, APP_VERSION


class MainWindow(QMainWindow):
    """Uygulamanin ana penceresi."""

    def __init__(self):
        super().__init__()
        self.config = AppConfig()
        self._dataset = None
        self._canvas_focus = False   # Gorsel odak modu aktif mi

        self._setup_ui()
        self._setup_controllers()
        self._setup_tools()
        self._setup_menus()
        self._setup_toolbar_actions()
        self._setup_dock_panels()
        self._connect_signals()
        self._restore_window_state()
        self._apply_dark_theme()

    # ─── UI Kurulum ───────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1280, 800)

        # Canvas
        self.scene = CanvasScene(self)
        self.canvas_view = CanvasView(self.scene, self)
        self.setCentralWidget(self.canvas_view)

        # Durum cubugu
        self._setup_status_bar()

    def _setup_status_bar(self):
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.label_tool = QLabel("Araç: Seç")
        self.label_pos = QLabel("X: 0  Y: 0")
        self.label_zoom = QLabel("Zoom: 100%")
        self.label_image_info = QLabel("")
        self.label_annotation_count = QLabel("Etiket: 0")

        self.status_bar.addWidget(self.label_tool)
        self.status_bar.addWidget(self._sep())
        self.status_bar.addWidget(self.label_pos)
        self.status_bar.addWidget(self._sep())
        self.status_bar.addWidget(self.label_zoom)
        self.status_bar.addPermanentWidget(self.label_annotation_count)
        self.status_bar.addPermanentWidget(self.label_image_info)

        self.canvas_view.mouse_scene_pos_changed.connect(self._update_mouse_pos)
        self.canvas_view.zoom_changed.connect(self._update_zoom_label)

    def _sep(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(20)
        return w

    # ─── Controller'lar ───────────────────────────────────────────────────────

    def _setup_controllers(self):
        self.ann_ctrl = AnnotationController(
            self.scene,
            self._write_image_labels,
            self
        )
        self.ds_ctrl = DatasetController(self.ann_ctrl, self, self)
        self.autosave_ctrl = AutosaveController(self.ds_ctrl, self.config, self)
        self._undo_stack = self.ann_ctrl.undo_stack

    def _write_image_labels(self, image):
        if self._dataset:
            from src.io.label_writer import write_label_file
            label_path = self._dataset.get_label_path_for_image(image)
            if label_path:
                write_label_file(label_path, image.annotations)
                image.mark_clean()

    # ─── Araclar ──────────────────────────────────────────────────────────────

    def _setup_tools(self):
        self._tools = {
            "Seç":          SelectTool(self.canvas_view, self.scene, self.ann_ctrl),
            "BBox":         BBoxTool(self.canvas_view, self.scene, self.ann_ctrl),
            "Polygon":      PolygonTool(self.canvas_view, self.scene, self.ann_ctrl),
            "OBB":          OBBTool(self.canvas_view, self.scene, self.ann_ctrl),
            "Keypoint":     KeypointTool(self.canvas_view, self.scene, self.ann_ctrl),
            "Sınıflandır":  ClassifyTool(self.canvas_view, self.scene, self.ann_ctrl),
        }
        self.canvas_view.set_tool(self._tools["Seç"])
        self._active_tool_name = "Seç"

        # Güvenilir araç kısayolları — QShortcut pencere düzeyinde her zaman çalışır
        _shortcuts = [
            ("V", "Seç"), ("B", "BBox"), ("P", "Polygon"),
            ("O", "OBB"), ("K", "Keypoint"), ("C", "Sınıflandır"),
        ]
        for key, name in _shortcuts:
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(lambda n=name: self._select_tool(n))

    def _select_tool(self, name: str):
        tool = self._tools.get(name)
        if tool:
            self.canvas_view.set_tool(tool)
            self._active_tool_name = name
            self.label_tool.setText(f"Araç: {name}")
            if hasattr(self, 'toolbar'):
                self.toolbar.select_tool(name)

    # ─── Menu ─────────────────────────────────────────────────────────────────

    def _setup_menus(self):
        mb = self.menuBar()

        file_menu = mb.addMenu("&Dosya")
        self._add_action(file_menu, "Yeni Veri Seti...", "Ctrl+N", self._on_new_dataset)
        self._add_action(file_menu, "Veri Seti Aç...", "Ctrl+O", self._on_open_dataset)
        self._add_action(file_menu, "Klasör Aç...", "Ctrl+Shift+O", self._on_open_folder)
        file_menu.addSeparator()
        self._add_action(file_menu, "Görsel İmport Et...", "Ctrl+I", self._on_import_images)
        file_menu.addSeparator()
        self._add_action(file_menu, "Kaydet", "Ctrl+S", self._on_save)
        self._add_action(file_menu, "Tümünü Kaydet", "Ctrl+Shift+S", self._on_save_all)
        file_menu.addSeparator()
        self._add_action(file_menu, "Dışarı Aktar...", "Ctrl+E", self._on_export)
        file_menu.addSeparator()
        self.recent_menu = file_menu.addMenu("Son Açılanlar")
        self._update_recent_menu()
        file_menu.addSeparator()
        self._add_action(file_menu, "Çıkış", "Alt+F4", self.close)

        edit_menu = mb.addMenu("&Düzenle")
        self.action_undo = self._add_action(edit_menu, "Geri Al", "Ctrl+Z", self._on_undo)
        self.action_redo = self._add_action(edit_menu, "Yinele", "Ctrl+Shift+Z", self._on_redo)
        edit_menu.addSeparator()
        self._add_action(edit_menu, "Seçili Etiketi Sil", "Delete", self._on_delete)
        edit_menu.addSeparator()
        self._add_action(edit_menu, "Ayarlar...", "Ctrl+,", self._on_settings)

        view_menu = mb.addMenu("&Görünüm")
        self._add_action(view_menu, "Yakınlaştır", "Ctrl+=", self.canvas_view.zoom_in)
        self._add_action(view_menu, "Uzaklaştır", "Ctrl+-", self.canvas_view.zoom_out)
        self._add_action(view_menu, "Pencereye Sığdır", "Ctrl+0", self.canvas_view.zoom_fit)
        self._add_action(view_menu, "%100 Zoom", "Ctrl+1", self.canvas_view.zoom_100)
        view_menu.addSeparator()
        self._add_action(view_menu, "Tam Ekran", "F11", self._on_fullscreen)
        self._add_action(view_menu, "Görsel Odak Modu", "F12", self._toggle_canvas_focus)

        nav_menu = mb.addMenu("&Navigasyon")
        self._add_action(nav_menu, "Önceki Görsel", "A", self.ds_ctrl.prev_image)
        self._add_action(nav_menu, "Sonraki Görsel", "D", self.ds_ctrl.next_image)

        help_menu = mb.addMenu("&Yardım")
        self._add_action(help_menu, "Kısayollar", "F1", self._on_shortcuts)
        self._add_action(help_menu, "Hakkında", None, self._on_about)

    def _add_action(self, menu, text, shortcut=None, slot=None) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        if slot:
            action.triggered.connect(slot)
        menu.addAction(action)
        return action

    # ─── Toolbar ──────────────────────────────────────────────────────────────

    def _setup_toolbar_actions(self):
        self.toolbar = MainToolbar(self)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)
        self.toolbar.tool_selected.connect(self._select_tool)
        self.toolbar.zoom_in_requested.connect(self.canvas_view.zoom_in)
        self.toolbar.zoom_out_requested.connect(self.canvas_view.zoom_out)
        self.toolbar.zoom_fit_requested.connect(self.canvas_view.zoom_fit)
        self.toolbar.zoom_100_requested.connect(self.canvas_view.zoom_100)
        self.toolbar.split_changed.connect(self._on_split_changed)

    # ─── Dock Panelleri ───────────────────────────────────────────────────────

    def _setup_dock_panels(self):
        self.image_list_panel = ImageListPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.image_list_panel)

        self.class_panel = ClassListPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.class_panel)

        self.ann_list_panel = AnnotationListPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.ann_list_panel)

        self.props_panel = PropertiesPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.props_panel)
        self.tabifyDockWidget(self.ann_list_panel, self.props_panel)

        self.ann_ctrl.set_annotation_list_panel(self.ann_list_panel)

    # ─── Sinyaller ────────────────────────────────────────────────────────────

    def _connect_signals(self):
        self.ds_ctrl.dataset_loaded.connect(self._on_dataset_loaded)
        self.ds_ctrl.error_occurred.connect(
            lambda msg: QMessageBox.critical(self, "Hata", msg)
        )
        self.image_list_panel.image_selected.connect(self.ds_ctrl.load_image)
        self.image_list_panel.import_requested.connect(self._on_import_images_for_split)
        self.class_panel.class_selected.connect(self.ann_ctrl.set_active_class)
        self.class_panel.class_changed.connect(self._on_class_changed)
        self.ann_list_panel.annotation_selected.connect(self._on_annotation_selected)
        self.ann_list_panel.annotation_delete_requested.connect(self._delete_annotation)
        self.ann_ctrl.annotations_loaded.connect(self._on_annotations_loaded)
        self.ann_ctrl.annotation_created.connect(self._on_annotation_changed)
        self.ann_ctrl.annotation_deleted.connect(self._on_annotation_changed)
        self.ann_ctrl.annotation_modified.connect(self._refresh_props_panel)
        self.scene.selectionChanged.connect(self._on_canvas_selection_changed)
        self.canvas_view.context_menu_requested.connect(self._on_annotation_context_menu)
        self._undo_stack.canUndoChanged.connect(
            lambda can: self.action_undo.setEnabled(can)
        )
        self._undo_stack.canRedoChanged.connect(
            lambda can: self.action_redo.setEnabled(can)
        )
        self.action_undo.setEnabled(False)
        self.action_redo.setEnabled(False)

        # ESC: tam ekran / gorsel odak modundan cik
        # (Pencere duzeyinde calısır — cizim iptali araclarda ayrica ele alinir)
        sc_esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        sc_esc.setContext(Qt.ShortcutContext.WindowShortcut)
        sc_esc.activated.connect(self._on_escape_press)

    # ─── Event Handler'lar ────────────────────────────────────────────────────

    def _on_dataset_loaded(self, dataset):
        self._dataset = dataset
        self.ann_ctrl.set_dataset(dataset)
        self.class_panel.set_dataset(dataset)
        self.props_panel.set_dataset(dataset)
        images = dataset.get_all_images()
        self.image_list_panel.load_images(images)
        if dataset.classes:
            self.ann_ctrl.set_active_class(0)
            self.class_panel._list.setCurrentRow(0)
            self.class_panel.raise_()  # Sınıflar panelini öne getir
            n = len(dataset.classes)
            self.status_bar.showMessage(
                f"{n} sınıf data.yaml'dan yüklendi  |  {len(images)} görsel bulundu", 5000
            )
        else:
            self.status_bar.showMessage(
                f"{len(images)} görsel yüklendi  (data.yaml'da sınıf tanımı bulunamadı)", 5000
            )

    def _on_annotations_loaded(self, image):
        """Gorsel degistiginde onceden yuklu annotationlari gunceller."""
        if image and self._dataset:
            self.ann_list_panel.load_annotations(
                image.annotations, self._dataset.classes
            )
            self.label_annotation_count.setText(f"Etiket: {len(image.annotations)}")
            self.image_list_panel.refresh_item(image)
            # Toolbar'daki split secicisini senkronize et
            if hasattr(self, 'toolbar') and self.toolbar.split_selector:
                self.toolbar.split_selector.set_split(image.split)

    def _on_annotation_changed(self, image, annotation):
        if image and self._dataset:
            self.ann_list_panel.load_annotations(
                image.annotations, self._dataset.classes
            )
            self.label_annotation_count.setText(f"Etiket: {len(image.annotations)}")
            self.image_list_panel.refresh_item(image)

    def _refresh_props_panel(self, image, annotation):
        self.props_panel.show_annotation(annotation)

    def _on_annotation_selected(self, annotation):
        item = self.ann_ctrl._ann_to_item.get(annotation.uid)
        if item:
            self.scene.clearSelection()
            item.setSelected(True)
        self.props_panel.show_annotation(annotation, item)

    def _on_canvas_selection_changed(self):
        selected = self.scene.selectedItems()
        if selected:
            item = selected[0]
            ann = self.ann_ctrl._item_to_ann.get(id(item))
            if ann:
                self.ann_list_panel.select_annotation(ann)
                self.props_panel.show_annotation(ann, item)
        else:
            self.props_panel.clear()

    def _on_split_changed(self, split: str):
        current = self.ds_ctrl._current_image
        if current:
            current.split = split
            current.mark_dirty()
            self.image_list_panel.refresh_item(current)

    def _on_class_changed(self, cls):
        if not self._dataset or not self.ds_ctrl._current_image:
            return
        for ann in self.ds_ctrl._current_image.annotations:
            if ann.class_id == cls.id:
                item = self.ann_ctrl._ann_to_item.get(ann.uid)
                if item:
                    item.class_name = cls.name
                    item.class_color = cls.color
                    if hasattr(item, 'update_from_annotation'):
                        item.update_from_annotation()

    def _on_annotation_context_menu(self, canvas_item, global_pos):
        """Canvas üzerinde bir etikete sağ tık yapıldığında sınıf değiştirme menüsü gösterir."""
        if not self._dataset:
            return
        ann = self.ann_ctrl._item_to_ann.get(id(canvas_item))
        if ann is None:
            return

        menu = QMenu(self)
        menu.setTitle("Sınıf Değiştir")

        for cls in self._dataset.classes:
            marker = "✓ " if cls.id == ann.class_id else "    "
            action = menu.addAction(f"{marker}[{cls.id}] {cls.name}")
            action.triggered.connect(
                lambda checked=False, c=cls, a=ann, it=canvas_item:
                    self.ann_ctrl.change_annotation_class(a, it, c.id)
            )

        menu.exec(global_pos)

    def _delete_annotation(self, annotation):
        item = self.ann_ctrl._ann_to_item.get(annotation.uid)
        if item:
            from src.commands.delete_annotation_cmd import DeleteAnnotationCommand
            cmd = DeleteAnnotationCommand(
                self.ds_ctrl._current_image, annotation, item, self.ann_ctrl
            )
            self._undo_stack.push(cmd)

    # ─── Menu Handler'lar ─────────────────────────────────────────────────────

    def _on_new_dataset(self):
        dlg = NewDatasetDialog(self)
        if dlg.exec():
            result = dlg.get_result()
            from src.models.dataset import Dataset
            dataset = Dataset()
            dataset.classes = result["classes"]
            if create_dataset_structure(result["root_path"], dataset):
                self.ds_ctrl._load_dataset(dataset)
                QMessageBox.information(self, "Başarılı", "Veri seti oluşturuldu.")
            else:
                QMessageBox.critical(self, "Hata", "Veri seti oluşturulamadı.")

    def _on_open_dataset(self):
        folder = QFileDialog.getExistingDirectory(self, "YOLO Veri Seti Klasörü Seç")
        if folder:
            self.ds_ctrl.open_dataset(folder)
            self.config.add_recent_file(folder)
            self._update_recent_menu()

    def _on_open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Görsel Klasörü Seç")
        if folder:
            self.ds_ctrl.open_folder(folder)

    def _on_save(self):
        self.ds_ctrl.save_current_image()
        self.status_bar.showMessage("Kaydedildi.", 2000)

    def _on_save_all(self):
        self.ds_ctrl.save_all()
        self.status_bar.showMessage("Tümü kaydedildi.", 2000)

    def _on_import_images(self, default_split="unassigned"):
        """Menüden 'Görsel İmport Et' seçildiğinde çalışır."""
        # triggered sinyali bool gecebilir; str olmasi gerekiyor
        if not isinstance(default_split, str):
            default_split = "unassigned"

        # Veri seti henuz acilmamissa dogrudan klasor ac (gecici mod)
        # Hem duz klasor hem YOLO images/+labels/ yapisi otomatik algilanir
        if not self._dataset:
            folder = QFileDialog.getExistingDirectory(
                self, "Görsel Klasörü Seç"
            )
            if folder:
                self.ds_ctrl.open_folder(folder)
            return

        dlg = ImportDialog(default_split=default_split, parent=self)
        if dlg.exec():
            added = self.ds_ctrl.import_images_from_folder(
                dlg.get_folder(), dlg.get_split(), dlg.get_mode()
            )
            if added > 0:
                self.status_bar.showMessage(
                    f"{added} görsel import edildi.", 4000
                )
            else:
                self.status_bar.showMessage(
                    "Import edilecek yeni görsel bulunamadı.", 3000
                )

    def _on_import_images_for_split(self, split: str):
        """image_list_panel'den 'İmport Et' sinyali geldiğinde çalışır."""
        effective = split if split != "all" else "unassigned"
        self._on_import_images(default_split=effective)

    def _on_export(self):
        if not self._dataset:
            QMessageBox.information(self, "Bilgi", "Önce bir veri seti açın.")
            return
        dlg = ExportDialog(self)
        if dlg.exec():
            path = dlg.get_export_path()
            copy = dlg.get_copy_images()
            if export_dataset(self._dataset, path, copy):
                QMessageBox.information(self, "Başarılı", f"Dışa aktarma tamamlandı:\n{path}")
            else:
                QMessageBox.critical(self, "Hata", "Dışa aktarma hatası oluştu.")

    def _on_undo(self):
        self._undo_stack.undo()

    def _on_redo(self):
        self._undo_stack.redo()

    def _on_delete(self):
        self.ann_ctrl.delete_selected()

    def _on_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            self.autosave_ctrl.restart()
            self.canvas_view.set_show_crosshair(self.config.show_crosshair)

    def _on_shortcuts(self):
        QMessageBox.information(self, "Klavye Kısayolları",
            "<table>"
            "<tr><td><b>V</b></td><td>Seçim Aracı</td></tr>"
            "<tr><td><b>B</b></td><td>BBox Aracı</td></tr>"
            "<tr><td><b>P</b></td><td>Polygon Aracı</td></tr>"
            "<tr><td><b>O</b></td><td>OBB Aracı</td></tr>"
            "<tr><td><b>K</b></td><td>Keypoint Aracı</td></tr>"
            "<tr><td><b>C</b></td><td>Sınıflandırma Aracı</td></tr>"
            "<tr><td><b>A / D</b></td><td>Önceki / Sonraki Görsel</td></tr>"
            "<tr><td><b>Delete</b></td><td>Seçili Etiketi Sil</td></tr>"
            "<tr><td><b>Ctrl+Z</b></td><td>Geri Al</td></tr>"
            "<tr><td><b>Ctrl+Shift+Z</b></td><td>Yinele</td></tr>"
            "<tr><td><b>Ctrl+S</b></td><td>Kaydet</td></tr>"
            "<tr><td><b>Ctrl+O</b></td><td>Veri Seti Aç</td></tr>"
            "<tr><td><b>Ctrl+E</b></td><td>Dışa Aktar</td></tr>"
            "<tr><td><b>Ctrl+=</b></td><td>Yakınlaştır</td></tr>"
            "<tr><td><b>Ctrl+-</b></td><td>Uzaklaştır</td></tr>"
            "<tr><td><b>Ctrl+0</b></td><td>Sığdır</td></tr>"
            "<tr><td><b>F11</b></td><td>Tam Ekran</td></tr>"
            "<tr><td><b>F12</b></td><td>Görsel Odak Modu (panelleri gizle)</td></tr>"
            "<tr><td><b>ESC</b></td><td>Tam Ekran / Odak Modundan Çık</td></tr>"
            "<tr><td><b>Ctrl+Tekerlek</b></td><td>Zoom</td></tr>"
            "<tr><td><b>Sol Tuş Sürükle</b></td><td>Pan (Seçim aracında boş alana)</td></tr>"
            "<tr><td><b>Orta Tuş Sürükle</b></td><td>Pan</td></tr>"
            "<tr><td><b>Esc</b></td><td>Çizimi İptal</td></tr>"
            "<tr><td><b>Enter</b></td><td>Polygon Kapat</td></tr>"
            "</table>")

    def _on_escape_press(self):
        """ESC: tam ekrandan veya gorsel odak modundan cikar."""
        if self._canvas_focus:
            self._exit_canvas_focus()
        if self.isFullScreen():
            self.showNormal()

    def _on_fullscreen(self):
        """F11: tam ekran / normal pencere arasinda gecis yapar."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _toggle_canvas_focus(self):
        """F12: gorsel odak modu – tum panelleri gizler, sadece canvas kalir."""
        if self._canvas_focus:
            self._exit_canvas_focus()
        else:
            self._enter_canvas_focus()

    def _enter_canvas_focus(self):
        """Gorsel odak moduna girer: panel, toolbar ve menuleri gizler."""
        self._canvas_focus = True
        self.image_list_panel.hide()
        self.class_panel.hide()
        self.ann_list_panel.hide()
        self.props_panel.hide()
        self.toolbar.hide()
        self.status_bar.hide()
        self.menuBar().hide()

    def _exit_canvas_focus(self):
        """Gorsel odak modundan cikar: tum panelleri geri getirir."""
        self._canvas_focus = False
        self.image_list_panel.show()
        self.class_panel.show()
        self.ann_list_panel.show()
        self.props_panel.show()
        self.toolbar.show()
        self.status_bar.show()
        self.menuBar().show()

    def _on_about(self):
        QMessageBox.about(self, "Hakkında",
            f"<h2>{APP_NAME}</h2>"
            f"<p>Sürüm: {APP_VERSION}</p>"
            f"<p>YOLO formatında görsel etiketleme uygulaması.</p>"
            f"<ul><li>Detection (BBox)</li><li>Segmentation (Polygon)</li>"
            f"<li>OBB</li><li>Pose (Keypoint)</li><li>Classification</li></ul>"
            f"<p>YOLO26 dahil tüm YOLO sürümleriyle uyumlu.</p>")

    def _update_recent_menu(self):
        self.recent_menu.clear()
        for path in self.config.recent_files:
            action = QAction(path, self)
            action.triggered.connect(lambda checked, p=path: self.ds_ctrl.open_dataset(p))
            self.recent_menu.addAction(action)
        if not self.config.recent_files:
            a = QAction("(bos)", self)
            a.setEnabled(False)
            self.recent_menu.addAction(a)

    # ─── Durum cubugu ─────────────────────────────────────────────────────────

    def _update_mouse_pos(self, x: float, y: float):
        self.label_pos.setText(f"X: {x:.0f}  Y: {y:.0f}")

    def _update_zoom_label(self, zoom: float):
        self.label_zoom.setText(f"Zoom: {zoom * 100:.0f}%")

    def update_tool_label(self, text: str):
        self.label_tool.setText(f"Arac: {text}")

    def update_image_info(self, info: str):
        self.label_image_info.setText(info)

    def update_annotation_count(self, count: int):
        self.label_annotation_count.setText(f"Etiket: {count}")

    def set_dataset(self, dataset):
        self._dataset = dataset
        if dataset and dataset.root_path:
            self.setWindowTitle(f"{APP_NAME} - {dataset.root_path.name}")

    # ─── Kapatma ──────────────────────────────────────────────────────────────

    def _restore_window_state(self):
        try:
            geometry = self.config.load_window_geometry()
            state = self.config.load_window_state()
            if geometry:
                self.restoreGeometry(geometry)
            else:
                self.resize(1400, 900)
            if state:
                self.restoreState(state)
        except Exception:
            self.resize(1400, 900)

    def closeEvent(self, event):
        self.config.save_window_state(self.saveGeometry(), self.saveState())
        if self._dataset:
            dirty = self._dataset.get_dirty_images()
            if dirty:
                reply = QMessageBox.question(
                    self, "Kaydedilmemiş Değişiklikler",
                    f"{len(dirty)} görselde kaydedilmemiş değişiklik var.\nKaydetmek ister misiniz?",
                    QMessageBox.StandardButton.Save |
                    QMessageBox.StandardButton.Discard |
                    QMessageBox.StandardButton.Cancel
                )
                if reply == QMessageBox.StandardButton.Save:
                    self._on_save_all()
                elif reply == QMessageBox.StandardButton.Cancel:
                    event.ignore()
                    return
        event.accept()

    # ─── Tema ─────────────────────────────────────────────────────────────────

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            * { font-family: "Segoe UI", sans-serif; }
            QMainWindow, QWidget { background-color: #1e1e1e; color: #cccccc; }
            QMenuBar { background-color: #2d2d2d; color: #cccccc; border-bottom: 1px solid #3d3d3d; }
            QMenuBar::item:selected { background-color: #094771; }
            QMenu { background-color: #2d2d2d; color: #cccccc; border: 1px solid #3d3d3d; }
            QMenu::item:selected { background-color: #094771; }
            QMenu::separator { height: 1px; background: #3d3d3d; }
            QToolBar { background-color: #2d2d2d; border-bottom: 1px solid #3d3d3d; spacing: 2px; padding: 2px; }
            QToolBar QToolButton { background: transparent; color: #cccccc; border: 1px solid transparent;
                border-radius: 4px; padding: 4px 10px; min-width: 32px; min-height: 28px; }
            QToolBar QToolButton:hover { background: #3d3d3d; border: 1px solid #4d4d4d; }
            QToolBar QToolButton:checked { background: #094771; border: 1px solid #1177bb; }
            QStatusBar { background: #2d2d2d; color: #888; border-top: 1px solid #3d3d3d; font-size: 11px; }
            QDockWidget { background: #252526; color: #ccc; }
            QDockWidget::title { background: #2d2d2d; padding: 5px; border: 1px solid #3d3d3d; }
            QListWidget, QTreeWidget { background: #1e1e1e; color: #ccc; border: 1px solid #3d3d3d; outline: none; }
            QListWidget::item { padding: 2px; }
            QListWidget::item:selected, QTreeWidget::item:selected { background: #094771; }
            QListWidget::item:hover, QTreeWidget::item:hover { background: #2a2d2e; }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                background: #3c3c3c; color: #ccc; border: 1px solid #3d3d3d; border-radius: 3px; padding: 4px; }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border: 1px solid #1177bb; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background: #2d2d2d; color: #ccc; selection-background-color: #094771; }
            QPushButton { background: #0e639c; color: #fff; border: none; border-radius: 3px; padding: 6px 14px; }
            QPushButton:hover { background: #1177bb; }
            QPushButton:pressed { background: #094771; }
            QScrollBar:vertical { background: #1e1e1e; width: 10px; }
            QScrollBar::handle:vertical { background: #424242; min-height: 20px; border-radius: 5px; }
            QScrollBar::handle:vertical:hover { background: #525252; }
            QScrollBar:horizontal { background: #1e1e1e; height: 10px; }
            QScrollBar::handle:horizontal { background: #424242; min-width: 20px; border-radius: 5px; }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
            QGroupBox { color: #ccc; border: 1px solid #3d3d3d; border-radius: 4px;
                margin-top: 8px; padding-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; padding: 0 4px; color: #888; }
            QTabWidget::pane { border: 1px solid #3d3d3d; background: #1e1e1e; }
            QTabBar::tab { background: #2d2d2d; color: #999; padding: 6px 14px;
                border: 1px solid #3d3d3d; border-bottom: none; }
            QTabBar::tab:selected { background: #1e1e1e; color: #ccc; border-bottom: 2px solid #1177bb; }
            QSplitter::handle { background: #3d3d3d; }
            QDialog { background: #1e1e1e; }
            QCheckBox { color: #ccc; }
            QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #555;
                border-radius: 2px; background: #3c3c3c; }
            QCheckBox::indicator:checked { background: #0e639c; border-color: #1177bb; }
            QLabel { color: #ccc; }
            QScrollArea { border: none; }
        """)
