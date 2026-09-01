"""Hesap (giris/kayit) kontrolcusu — Faz 2.

Bulut/auth katmanini (src.cloud) UI'a baglar. Bulut yapilandirilmamissa
veya supabase paketi yoksa hesap menusu bilgilendirici/pasif olur; yerel
(bireysel) calisma modu hicbir sekilde etkilenmez.

Auth cagrilari (giris/kayit/oturum geri yukleme) ag islemleridir; UI'in
donmamasi icin arka plan thread'inde (_AuthWorker) calistirilir.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal, QTimer
from PySide6.QtGui import QAction

from src.cloud.cloud_config import CloudConfig
from src.cloud import supabase_client


class _AuthWorker(QThread):
    """Tek bir auth cagrisini arka planda calistirir."""

    done = Signal(object)    # fonksiyon sonucu
    failed = Signal(str)     # hata mesaji

    def __init__(self, fn: Callable, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            result = self._fn()
        except Exception as exc:  # AuthError dahil
            self.failed.emit(str(exc))
            return
        self.done.emit(result)


class AccountController(QObject):
    """Ana penceredeki 'Hesap' menusunu ve oturum durumunu yonetir."""

    auth_changed = Signal()

    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window
        self._auth = None            # AuthManager | None
        self._available = False      # bulut kullanilabilir mi
        self._menu = None
        self._workers = []           # canli QThread referanslari (GC korumasi)
        # Ekip dataseti (write-through) durumu
        self._img_svc = None
        self._open_worker = None
        self._cloud_active = False
        self._cloud_dir = None
        self._cloud_dataset_id = None
        self._cloud_map = {}
        self._cloud_meta = {}
        self._cloud_hash = {}        # filename → content_hash (lazy indirme)
        self._storage_client = None  # StorageClient (keep-alive havuzu)
        # Sınıf değişikliklerini DB'ye yazma (debounce)
        self._class_signals_connected = False
        self._class_persist_timer = QTimer(self)
        self._class_persist_timer.setSingleShot(True)
        self._class_persist_timer.timeout.connect(self._do_persist_cloud_classes)
        self._init_backend()
        # Editör kaydetme → DB write-through köprüsü
        try:
            self.mw.ds_ctrl.image_saved.connect(self._on_cloud_image_saved)
            self.mw.ds_ctrl.image_deleted.connect(self._on_cloud_image_deleted)
            self.mw.ds_ctrl.image_restored.connect(self._on_cloud_image_restored)
            self.mw.ds_ctrl.dataset_loaded.connect(self._on_any_dataset_loaded)
        except Exception:
            pass

    def _init_backend(self):
        cfg = CloudConfig.load()
        if not (cfg.is_configured() and supabase_client.is_available()):
            self._available = False
            return
        try:
            from src.cloud.auth import AuthManager
            self._auth = AuthManager()
            self._available = True
        except Exception:
            self._auth = None
            self._available = False

    # ─── Menu ──────────────────────────────────────────────────────────────
    def build_menu(self, menubar):
        self._menu = menubar.addMenu("&Hesap")
        self._refresh_menu()
        return self._menu

    def _refresh_menu(self):
        if self._menu is None:
            return
        self._menu.clear()

        if not self._available:
            self._add_disabled("Bulut yapılandırılmamış")
            self._add_disabled("Kurulum: docs/SUPABASE_KURULUM.md")
            return

        if self._auth and self._auth.is_authenticated():
            u = self._auth.user
            label = (u.display_name or u.username or u.email or "Kullanıcı") if u else "Kullanıcı"
            self._add_disabled(f"Giriş yapıldı: {label}")
            self._menu.addSeparator()
            workspace = QAction("Ekip Çalışması...", self.mw)
            workspace.triggered.connect(self._on_workspace)
            self._menu.addAction(workspace)
            teams = QAction("Ekiplerim...", self.mw)
            teams.triggered.connect(self._on_teams)
            self._menu.addAction(teams)
            self._menu.addSeparator()
            out = QAction("Çıkış Yap", self.mw)
            out.triggered.connect(self._on_logout)
            self._menu.addAction(out)
        else:
            login = QAction("Giriş Yap / Kayıt Ol...", self.mw)
            login.triggered.connect(self._on_login)
            self._menu.addAction(login)

    def _add_disabled(self, text: str):
        act = QAction(text, self.mw)
        act.setEnabled(False)
        self._menu.addAction(act)

    # ─── Baslangic: oturum geri yukleme ────────────────────────────────────
    def start(self):
        """Kayitli token varsa oturumu arka planda geri yukler."""
        if not self._available or self._auth is None:
            return
        worker = _AuthWorker(self._auth.restore_session, self)
        worker.done.connect(self._on_restored)
        worker.failed.connect(lambda _m: None)
        self._track(worker)
        worker.start()

    def _on_restored(self, user):
        self._refresh_menu()
        self.auth_changed.emit()
        if user is not None:
            name = user.display_name or user.username or user.email
            self.mw.status_bar.showMessage(f"Bulut oturumu geri yüklendi: {name}", 4000)

    # ─── Eylemler ──────────────────────────────────────────────────────────
    def _on_login(self):
        from src.widgets.auth_dialog import AuthDialog
        dlg = AuthDialog(self._auth, self.mw)
        if dlg.exec():
            self._refresh_menu()
            self.auth_changed.emit()
            u = self._auth.user
            if u:
                name = u.display_name or u.username or u.email
                self.mw.status_bar.showMessage(f"Giriş yapıldı: {name}", 4000)

    def _on_teams(self):
        if not self.is_authenticated():
            return
        from src.widgets.teams_dialog import TeamsDialog
        from src.cloud.teams import TeamService
        svc = TeamService(self._auth.user.id)
        TeamsDialog(svc, self.mw).exec()

    def _on_workspace(self):
        if not self.is_authenticated():
            return
        from src.widgets.team_workspace_dialog import TeamWorkspaceDialog
        TeamWorkspaceDialog(self._auth.user.id, self.mw,
                            on_open=self.open_cloud_dataset).exec()

    # ─── Ekip datasetini editörde açma + write-through ─────────────────────
    def open_cloud_dataset(self, ds: dict):
        if not self.is_authenticated():
            return
        from pathlib import Path
        from PySide6.QtWidgets import QProgressDialog
        from PySide6.QtCore import Qt
        from src.cloud.datasets import DatasetService
        from src.cloud.images import ImageService
        from src.cloud.storage import StorageClient
        from src.widgets.cloud_open_worker import CloudDatasetOpenWorker

        uid = self._auth.user.id
        dsvc = DatasetService(uid)
        self._img_svc = ImageService(uid)
        try:
            images = self._img_svc.list_images(ds["id"])
            classes = dsvc.list_classes(ds["id"])
        except Exception as exc:
            self.mw.status_bar.showMessage(f"Dataset bilgisi alınamadı: {exc}", 5000)
            return
        if not images:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self.mw, "Boş Dataset",
                                    "Bu datasette görsel yok. Önce görsel yükleyin.")
            return

        # Önceki ekip odasından çık (başka ekip dataseti açılıyorsa)
        try:
            if self.mw.collab_ctrl.is_in_lobby:
                self.mw.collab_ctrl.leave_lobby()
        except Exception:
            pass

        self._storage_client = StorageClient()
        self._cloud_hash = {im["filename"]: im["content_hash"] for im in images}
        self._cloud_meta = {im["filename"]: dict(im) for im in images}
        dest = Path.home() / ".annotie" / "cache" / "datasets" / ds["id"]

        # Lazy: yalnızca yapı + etiketler hazırlanır; görseller görüntülendikçe iner
        progress = QProgressDialog("Dataset hazırlanıyor...", None, 0, 0, self.mw)
        progress.setWindowTitle("Ekip Dataseti Açılıyor")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.show()

        worker = CloudDatasetOpenWorker(ds, images, classes, self._storage_client, dest,
                                        download_images=False, parent=self.mw)
        self._open_worker = worker

        def on_done(local_dir, mapping):
            progress.close()
            self._open_worker = None
            self._cloud_dir = local_dir
            self._cloud_dataset_id = ds["id"]
            self._cloud_map = mapping
            self._cloud_active = True
            dset = self._build_dataset_model(ds, images, classes, Path(local_dir))
            self._ensure_class_signals_connected()
            self.mw.ds_ctrl.set_ensure_local(self._ensure_cloud_image)
            self.mw.ds_ctrl.load_external_dataset(dset)
            self.mw.status_bar.showMessage(
                f"Ekip dataseti açıldı: {ds['name']} ({len(images)} görsel) — "
                "görseller görüntülendikçe iniyor", 6000)
            # Faz 7: canlı işbirliği odasına otomatik katıl (presence + canlı senkron)
            try:
                u = self._auth.user
                dn = u.display_name or u.username or u.email or "Kullanıcı"
                token = None
                try:
                    sess = supabase_client.get_client().auth.get_session()
                    token = sess.access_token if sess else None
                except Exception:
                    token = None
                self.mw.collab_ctrl.set_dataset(dset)
                self.mw.collab_ctrl.join_dataset_room(
                    self._collab_url(), ds["id"], dn, token=token)
            except Exception as exc:
                # Canlı ekip bağlantısı başarısız olursa sessizce yutma;
                # kullanıcı ekip datasetinin neden yalnız çalıştığını görsün.
                self.mw.status_bar.showMessage(
                    f"Canlı ekip bağlantısı başlatılamadı: {exc}", 6000
                )
                try:
                    self.mw.collab_ctrl.error_occurred.emit(str(exc))
                except Exception:
                    pass

        def on_failed(msg):
            progress.close()
            self._open_worker = None
            self.mw.status_bar.showMessage(f"Dataset açılamadı: {msg}", 5000)

        worker.done.connect(on_done)
        worker.failed.connect(on_failed)
        worker.start()

    def _build_dataset_model(self, ds, images, classes, local_dir):
        """DB metadata'sından Dataset nesnesi kurar (görseller henüz inmemiş)."""
        from pathlib import Path
        from PySide6.QtGui import QColor
        from src.models.dataset import Dataset
        from src.models.image_item import ImageItem
        from src.models.label_class import LabelClass
        from src.models.annotation import AnnotationType

        dset = Dataset(root_path=local_dir)
        for c in sorted(classes, key=lambda x: x.get("class_index", 0)):
            color = QColor(c["color"]) if c.get("color") else None
            dset.classes.append(
                LabelClass(id=int(c["class_index"]), name=c["name"], color=color))
        kpt = ds.get("kpt_shape")
        if kpt:
            dset.kpt_shape = tuple(kpt)
        tt = ds.get("task_type")
        if tt:
            try:
                dset.task_type = AnnotationType(tt)
            except ValueError:
                pass

        images_dir = local_dir / "images"
        labels_dir = local_dir / "labels"
        for im in images:
            fn = im["filename"]
            item = ImageItem(path=images_dir / fn,
                             split=im.get("split") or "unassigned")
            lbl = labels_dir / (Path(fn).stem + ".txt")
            if lbl.exists():
                item._pending_label_path = lbl
                item._pending_kpt_shape = dset.kpt_shape
            dset.add_image(item)
        return dset

    def _ensure_cloud_image(self, image):
        """Görsel diskte yoksa R2'den indirir (lazy fetch). load_image_at çağırır."""
        try:
            p = image.path
            if p.exists() or self._storage_client is None:
                return
            h = self._cloud_hash.get(image.filename)
            if not h:
                return
            import shutil
            from PySide6.QtWidgets import QApplication
            from PySide6.QtCore import Qt
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                blob = self._storage_client.download_to_cache(h)
                p.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(blob, p)
            finally:
                QApplication.restoreOverrideCursor()
        except Exception:
            pass

    # ─── Sınıf değişikliklerini DB'ye yazma ────────────────────────────────
    def _ensure_class_signals_connected(self):
        """class_panel sinyallerini (account_ctrl'den sonra kurulduğu için)
        bir kez bağlar."""
        if self._class_signals_connected:
            return
        try:
            cp = self.mw.class_panel
            cp.class_added.connect(self._on_cloud_classes_changed)
            cp.class_removed.connect(self._on_cloud_classes_changed)
            cp.class_changed.connect(self._on_cloud_classes_changed)
            self._class_signals_connected = True
        except Exception:
            pass

    def _on_cloud_classes_changed(self, *args):
        if not self._cloud_active or not self.is_authenticated():
            return
        self._class_persist_timer.start(800)   # debounce

    def _do_persist_cloud_classes(self):
        if not self._cloud_active or self._cloud_dataset_id is None:
            return
        ds = self.mw.ds_ctrl.dataset
        if not ds:
            return
        classes = [
            (c.name, c.color.name() if c.color else None)
            for c in ds.classes
        ]
        try:
            from src.cloud.datasets import DatasetService
            dsvc = DatasetService(self._auth.user.id)
            worker = _AuthWorker(
                lambda did=self._cloud_dataset_id, cls=classes:
                    dsvc.replace_classes(did, cls), self)
            worker.failed.connect(lambda _m: None)
            self._track(worker)
            worker.start()
        except Exception:
            pass

    def _on_cloud_image_saved(self, image):
        """Ekip dataseti aktifken kaydedilen etiketi DB'ye write-through eder."""
        if not self._cloud_active or not self.is_authenticated() or self._img_svc is None:
            return
        image_id = self._cloud_map.get(image.filename)
        if not image_id:
            return
        # Yerel etiket dosyasını oku
        content = ""
        try:
            ds = self.mw.ds_ctrl.dataset
            label_path = ds.get_label_path_for_image(image) if ds else None
            if label_path and label_path.exists():
                content = label_path.read_text(encoding="utf-8")
        except Exception:
            pass
        # Arka planda gönder (UI'yi her kayıtta bloke etme)
        worker = _AuthWorker(
            lambda iid=image_id, c=content: self._img_svc.update_label(iid, c), self)
        worker.failed.connect(lambda _m: None)
        self._track(worker)
        worker.start()

    def _on_cloud_image_deleted(self, image, delete_record=None):
        """Ekip datasetindeki yerel silmeyi Supabase images kaydına uygular."""
        if not self._cloud_active or not self.is_authenticated() or self._img_svc is None:
            return
        filename = image.filename
        image_id = self._cloud_map.get(filename)
        if not image_id:
            return

        worker = _AuthWorker(
            lambda iid=image_id: self._img_svc.delete_image(iid), self
        )

        def on_done(_result, fn=filename, iid=image_id):
            if self._cloud_map.get(fn) == iid:
                self._cloud_map.pop(fn, None)
            self.mw.status_bar.showMessage(
                f"Ekip datasetinden silindi: {fn}", 3500
            )

        def on_failed(message):
            self.mw.status_bar.showMessage(
                f"Ekip kaydı silinemedi: {message}", 6000
            )

        worker.done.connect(on_done)
        worker.failed.connect(on_failed)
        self._track(worker)
        worker.start()

    def _on_cloud_image_restored(self, image):
        """Geri alınan görselin Supabase images satırını yeniden kurar."""
        if not self._cloud_active or not self.is_authenticated() or self._img_svc is None:
            return
        meta = self._cloud_meta.get(image.filename)
        if not meta:
            return

        label_content = ""
        try:
            ds = self.mw.ds_ctrl.dataset
            label_path = ds.get_label_path_for_image(image) if ds else None
            if label_path and label_path.exists():
                label_content = label_path.read_text(encoding="utf-8")
        except Exception:
            pass

        worker = _AuthWorker(
            lambda m=dict(meta), c=label_content: self._img_svc.add_image(
                self._cloud_dataset_id,
                m["filename"],
                m["content_hash"],
                m.get("storage_key") or f"blobs/{m['content_hash']}",
                width=m.get("width"),
                height=m.get("height"),
                split=m.get("split"),
                size_bytes=m.get("size_bytes"),
                label_content=c,
            ), self
        )

        def on_done(row, fn=image.filename):
            if row and row.get("id"):
                self._cloud_map[fn] = row["id"]
            self.mw.status_bar.showMessage(
                f"Ekip datasetine geri eklendi: {fn}", 3500
            )

        def on_failed(message):
            self.mw.status_bar.showMessage(
                f"Ekip kaydı geri yüklenemedi: {message}", 6000
            )

        worker.done.connect(on_done)
        worker.failed.connect(on_failed)
        self._track(worker)
        worker.start()

    def _on_any_dataset_loaded(self, dataset):
        """Farklı (yerel) bir dataset açılırsa ekip write-through'u devre dışı bırak."""
        from pathlib import Path
        root = getattr(dataset, "root_path", None)
        if self._cloud_dir is None or root is None:
            self._cloud_active = False
            return
        try:
            same = Path(root).resolve() == Path(self._cloud_dir).resolve()
        except Exception:
            same = str(root) == str(self._cloud_dir)
        if not same:
            self._cloud_active = False
            self._cloud_dataset_id = None
            self._cloud_map.clear()
            self._cloud_meta.clear()
            self._cloud_hash.clear()
            # Yerel/başka datasete geçince ekip odasından çık
            try:
                if self.mw.collab_ctrl.is_in_lobby:
                    self.mw.collab_ctrl.leave_lobby()
            except Exception:
                pass

    @staticmethod
    def _collab_url() -> str:
        """Relay sunucu adresi. Yerel test: ws://127.0.0.1:8765/ws.
        COLLAB_URL ortam değişkeni veya cloud_config.json 'collab_url' ile değişir."""
        from src.cloud.cloud_config import CloudConfig
        return CloudConfig.load().get_collab_url()

    def _on_logout(self):
        if not self._auth:
            return
        self._auth.sign_out()
        self._refresh_menu()
        self.auth_changed.emit()
        self.mw.status_bar.showMessage("Çıkış yapıldı", 3000)

    # ─── Durum / yardimci ──────────────────────────────────────────────────
    @property
    def auth(self):
        return self._auth

    @property
    def available(self) -> bool:
        return self._available

    def is_authenticated(self) -> bool:
        return bool(self._auth and self._auth.is_authenticated())

    def current_user(self):
        return self._auth.user if self._auth else None

    def _track(self, worker: QThread):
        self._workers.append(worker)
        worker.finished.connect(lambda: self._untrack(worker))

    def _untrack(self, worker: QThread):
        if worker in self._workers:
            self._workers.remove(worker)
