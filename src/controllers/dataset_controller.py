"""Veriseti yukleme, kaydetme ve export yonetimi."""

from pathlib import Path
from PySide6.QtCore import QObject, Signal

from src.io.dataset_importer import import_dataset
from src.io.folder_importer import import_folder
from src.io.label_writer import write_label_file
from src.io.yaml_handler import write_data_yaml
from src.models.dataset import Dataset


class DatasetController(QObject):
    dataset_loaded = Signal(object)       # Dataset
    dataset_cleared = Signal()
    image_saved = Signal(object)          # ImageItem
    image_deleted = Signal(object, object)  # (ImageItem, delete_record)
    image_restored = Signal(object)       # ImageItem
    error_occurred = Signal(str)

    def __init__(self, annotation_controller, main_window, parent=None):
        super().__init__(parent)
        self._ann_ctrl = annotation_controller
        self._window = main_window
        self._dataset = None
        self._current_image = None
        self._image_list = []   # Siradaki gorsel listesi
        self._current_index = -1
        # Split bazlı son konum (0-bazlı indeks; -1 = hiç ziyaret edilmedi)
        self._split_positions = {
            "all": -1, "train": -1, "val": -1, "test": -1, "unassigned": -1
        }
        # Cloud lazy indirme kancası: load_image_at içinde, görsel diske
        # okunmadan önce çağrılır (ekip dataseti için görseli R2'den indirir).
        self._ensure_local = None

    @property
    def dataset(self) -> Dataset:
        return self._dataset

    def set_ensure_local(self, callback):
        """Görsel yüklenmeden önce çalışacak indirme kancası (veya None)."""
        self._ensure_local = callback

    def load_external_dataset(self, dataset: Dataset):
        """Dışarıda kurulmuş bir Dataset nesnesini yükler (cloud lazy için)."""
        self._load_dataset(dataset)

    def open_dataset(self, path: str):
        """YOLO veriseti klasorunu ac."""
        self._ensure_local = None   # yerel dataset: indirme kancası kapalı
        dataset = import_dataset(path)
        if dataset is None:
            self.error_occurred.emit(f"Veriseti acilamadi: {path}")
            return
        self._load_dataset(dataset)

    def open_folder(self, path: str):
        """Duz gorsel klasorunu ac (gecici mod)."""
        self._ensure_local = None
        dataset = import_folder(path)
        if dataset is None:
            self.error_occurred.emit(f"Klasor acilamadi: {path}")
            return
        self._load_dataset(dataset)

    def _load_dataset(self, dataset: Dataset):
        self._dataset = dataset
        self._ann_ctrl.set_dataset(dataset)
        self._image_list = dataset.get_all_images()
        self._current_index = -1
        # Konumları sıfırla (yeni veri seti için kalıcı konumlar sonradan set edilir)
        self._split_positions = {
            "all": -1, "train": -1, "val": -1, "test": -1, "unassigned": -1
        }
        # Ilk gorseli sinyal oncesi yukle — restore sonradan split pozisyonlarini ezmemesi icin
        if self._image_list:
            self.load_image_at(0)
        else:
            self._ann_ctrl.scene.clear_all()
            self._ann_ctrl.scene.setSceneRect(0, 0, 0, 0)

        self.dataset_loaded.emit(dataset)
        self._window.set_dataset(dataset)

    def load_image_at(self, index: int):
        """Belirli indisteki gorseli yukler."""
        if not self._image_list or index < 0 or index >= len(self._image_list):
            return

        # Gorsel degismeden once aktif araci sifirla:
        # Yari bitmis keypoint gibi annotation'lar otomatik kaydedilir
        try:
            cv = getattr(self._window, 'canvas_view', None)
            if cv:
                active_tool = cv.get_tool()
                if active_tool:
                    active_tool.deactivate()
                    active_tool.activate()
        except Exception:
            pass

        self._current_index = index
        image = self._image_list[index]
        self._current_image = image

        # Global ve split bazlı konumları güncelle
        self._split_positions["all"] = index
        split = image.split
        split_imgs = [img for img in self._image_list if img.split == split]
        try:
            self._split_positions[split] = split_imgs.index(image)
        except ValueError:
            pass

        # Lazy etiket yukleme: gorsel secildiginde etiketi oku
        had_pending = image._pending_label_path is not None
        image.load_pending_labels()
        if had_pending:
            img_panel = getattr(self._window, 'image_list_panel', None)
            if img_panel:
                img_panel.refresh_item(image)

        # Cloud lazy: görsel diskte yoksa indir (ekip dataseti)
        if self._ensure_local is not None:
            try:
                self._ensure_local(image)
            except Exception:
                pass

        # Gorseli canvas'a yukle
        image.load_dimensions()
        from src.io.image_loader import load_pixmap
        pixmap = load_pixmap(str(image.path))
        if not pixmap.isNull():
            self._ann_ctrl.scene.set_image(pixmap)

        self._ann_ctrl.set_current_image(image)

        # Sol panel secimini senkronize et (sinyal dongusune girmeden)
        img_panel = getattr(self._window, 'image_list_panel', None)
        if img_panel:
            img_panel.select_image_silent(image)

        # Durum cubuklarini guncelle
        split_str = {"train": "Eğitim", "val": "Doğrulama", "test": "Test"}.get(
            image.split, "Atanmamış"
        )
        self._window.update_image_info(
            f"{image.filename}  ({image.width}x{image.height})  [{split_str}]"
            f"  {self._current_index + 1}/{len(self._image_list)}"
        )
        self._window.canvas_view.zoom_fit()

    def load_image(self, image_item):
        """ImageItem ile gorsel yukler."""
        try:
            idx = self._image_list.index(image_item)
            self.load_image_at(idx)
        except ValueError:
            pass

    def next_image(self):
        if self._current_index < len(self._image_list) - 1:
            self.load_image_at(self._current_index + 1)

    def prev_image(self):
        if self._current_index > 0:
            self.load_image_at(self._current_index - 1)

    def next_labeled_image(self):
        """Etiket içeren bir sonraki görsele atlar (yön tuşu)."""
        for i in range(self._current_index + 1, len(self._image_list)):
            if self._image_list[i].has_labels:
                self.load_image_at(i)
                return

    def prev_labeled_image(self):
        """Etiket içeren bir önceki görsele atlar (yön tuşu)."""
        for i in range(self._current_index - 1, -1, -1):
            if self._image_list[i].has_labels:
                self.load_image_at(i)
                return

    def save_current_image(self):
        """Mevcut gorselin etiketlerini kaydeder."""
        if self._current_image:
            self._write_image_labels(self._current_image)

    def save_all(self):
        """Tum degismis gorsellerin etiketlerini kaydeder."""
        if not self._dataset:
            return
        for image in self._dataset.get_dirty_images():
            self._write_image_labels(image)
        # data.yaml guncelle
        if self._dataset.root_path:
            yaml_path = self._dataset.root_path / 'data.yaml'
            if not self._dataset.is_temporary:
                write_data_yaml(yaml_path, self._dataset)

    def _write_image_labels(self, image):
        """Tek gorsel icin etiket dosyasi yazar."""
        if not self._dataset:
            return
        label_path = self._dataset.get_label_path_for_image(image)
        if label_path is None:
            return
        identity_path = self._dataset.get_annotation_identity_path(label_path)
        if write_label_file(label_path, image.annotations, identity_path):
            image.mark_clean()
            self.image_saved.emit(image)

    def set_image_split(self, image, split: str):
        """Gorsel split atamasini degistirir."""
        if image:
            image.split = split

    def delete_image_from_disk(self, image):
        """Gorseli ve varsa etiket dosyasini diskten siler."""
        if not self._dataset or not image:
            return False, "Silinecek görsel bulunamadı.", None

        try:
            old_index = self._image_list.index(image)
        except ValueError:
            return False, "Görsel mevcut veri setinde bulunamadı.", None

        is_current = image is self._current_image
        self._ann_ctrl.discard_pending_save(image)
        if is_current:
            self._ann_ctrl.clear_current_image()

        paths_to_delete = []

        def _add_path(path):
            if path and path not in paths_to_delete:
                paths_to_delete.append(Path(path))

        _add_path(image.path)
        _add_path(self._dataset.get_label_path_for_image(image))
        _add_path(self._dataset.get_annotation_identity_path_for_image(image))
        _add_path(getattr(image, "_pending_label_path", None))
        _add_path(getattr(image, "_pending_identity_path", None))
        _add_path(image.path.with_suffix(".txt"))

        backups = {}
        for path in paths_to_delete:
            try:
                if path.exists() and path.is_file():
                    backups[path] = path.read_bytes()
            except OSError as exc:
                if is_current:
                    self.load_image_at(old_index)
                return False, f"Dosya okunamadı: {path}\n{exc}", None

        deleted_files = 0
        for path in paths_to_delete:
            try:
                if path.exists() and path.is_file():
                    path.unlink()
                    deleted_files += 1
            except OSError as exc:
                for restore_path, data in backups.items():
                    if not restore_path.exists():
                        try:
                            restore_path.parent.mkdir(parents=True, exist_ok=True)
                            restore_path.write_bytes(data)
                        except OSError:
                            pass
                if is_current:
                    self.load_image_at(old_index)
                return False, f"Dosya silinemedi: {path}\n{exc}", None

        self._dataset.remove_image(str(image.path))
        self._image_list = self._dataset.get_all_images()

        for split in self._split_positions:
            if self._split_positions[split] >= len(self._image_list):
                self._split_positions[split] = len(self._image_list) - 1

        if self._image_list:
            if is_current:
                next_index = min(old_index, len(self._image_list) - 1)
                self.load_image_at(next_index)
            elif self._current_image in self._image_list:
                self._current_index = self._image_list.index(self._current_image)
                self._split_positions["all"] = self._current_index
                current_split = self._current_image.split
                split_imgs = [img for img in self._image_list if img.split == current_split]
                if self._current_image in split_imgs:
                    self._split_positions[current_split] = split_imgs.index(self._current_image)
        else:
            self._current_image = None
            self._current_index = -1
            self._window.update_image_info("")

        delete_record = {
            "image": image,
            "index": old_index,
            "files": backups,
        }
        self.image_deleted.emit(image, delete_record)
        if deleted_files == 0:
            return True, "Görsel listeden kaldırıldı; diskte dosya bulunamadı.", delete_record
        if deleted_files == 1:
            return True, "Görsel diskten silindi.", delete_record
        return True, "Görsel ve etiket dosyası diskten silindi.", delete_record

    def restore_deleted_image(self, delete_record):
        """Kisa sureli geri alma icin silinen gorseli ve etiketini geri yazar."""
        if not self._dataset or not delete_record:
            return False, "Geri alınacak görsel bulunamadı."

        image = delete_record.get("image")
        files = delete_record.get("files", {})
        index = delete_record.get("index", len(self._image_list))
        if not image:
            return False, "Geri alınacak görsel bulunamadı."

        for path in files:
            if path.exists():
                return False, f"Geri alınamadı; dosya zaten var: {path}"

        try:
            for path, data in files.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        except OSError as exc:
            return False, f"Geri alma sırasında dosya yazılamadı:\n{exc}"

        images = self._image_list[:]
        if image not in images:
            index = max(0, min(index, len(images)))
            images.insert(index, image)
            self._dataset.images = {str(img.path): img for img in images}
        self._image_list = self._dataset.get_all_images()
        self.load_image(image)
        self.image_restored.emit(image)
        return True, "Görsel geri alındı."

    def import_images_from_folder(self, folder_path: str, split: str, mode: str) -> int:
        """Klasörden görselleri mevcut dataset'e import eder.

        Hem düz klasör hem YOLO yapısını (images/ + labels/) destekler.

        Args:
            folder_path: Görsel klasörü veya YOLO dataset kök klasörü yolu
            split: Hedef split ('train','val','test','unassigned','auto')
            mode: 'add' → mevcut görseller korunur; 'replace' → split sıfırlanır

        Returns:
            Eklenen görsel sayısı
        """
        if not self._dataset:
            return 0

        from pathlib import Path
        from src.io.label_reader import read_label_file
        from src.models.image_item import ImageItem
        from src.utils.constants import SUPPORTED_IMAGE_FORMATS

        folder = Path(folder_path)
        if not folder.exists():
            return 0

        # Split otomatik tespiti
        effective_split = split
        if split == "auto":
            name_lower = folder.name.lower()
            if "train" in name_lower:
                effective_split = "train"
            elif "val" in name_lower or "valid" in name_lower:
                effective_split = "val"
            elif "test" in name_lower:
                effective_split = "test"
            else:
                effective_split = "unassigned"

        # Yaz modu: seçili split'i temizle
        if mode == "replace" and effective_split not in ("all", "auto"):
            self._dataset.remove_images_by_split(effective_split)

        kpt_shape = getattr(self._dataset, 'kpt_shape', None)
        added = 0

        def _collect_in(d: Path):
            imgs = []
            for ext in SUPPORTED_IMAGE_FORMATS:
                imgs.extend(d.glob(f'*{ext}'))
                imgs.extend(d.glob(f'*{ext.upper()}'))
            return sorted(set(imgs))

        # YOLO yapisi mı? (images/ alt klasoru var)
        images_dir = folder / "images"
        labels_dir = folder / "labels"
        img_list = []   # list of (img_path, split_str, lbl_dir_or_None)

        if images_dir.exists() and images_dir.is_dir():
            direct = _collect_in(images_dir)
            if direct:
                # images/ icinde dogrudan gorseller
                img_list = [(p, effective_split, labels_dir) for p in direct]
            else:
                # images/ altinda split klasorleri
                for split_dir in sorted(images_dir.iterdir()):
                    if not split_dir.is_dir():
                        continue
                    sp_name = split_dir.name.lower()
                    if "train" in sp_name:
                        sp = "train"
                    elif "val" in sp_name or "valid" in sp_name:
                        sp = "val"
                    elif "test" in sp_name:
                        sp = "test"
                    else:
                        sp = effective_split
                    sp_lbl = labels_dir / split_dir.name if labels_dir.exists() else None
                    for p in _collect_in(split_dir):
                        img_list.append((p, sp, sp_lbl))
        else:
            # Duz klasor: recursive gorsel topla
            for ext in SUPPORTED_IMAGE_FORMATS:
                for p in folder.rglob(f'*{ext}'):
                    img_list.append((p, effective_split, None))
                for p in folder.rglob(f'*{ext.upper()}'):
                    img_list.append((p, effective_split, None))
            # Tekrar edenleri temizle ve sirala
            seen = set()
            unique = []
            for item in img_list:
                if item[0] not in seen:
                    seen.add(item[0])
                    unique.append(item)
            img_list = sorted(unique, key=lambda x: x[0])

        for img_path, img_split, lbl_dir in img_list:
            key = str(img_path)
            if key in self._dataset.images:
                continue  # Zaten var, atla

            item = ImageItem(path=img_path, split=img_split)

            # Etiket ara: once labels/ klasorundan, sonra gorsel yaninda
            if lbl_dir and Path(lbl_dir).exists():
                lbl_path = Path(lbl_dir) / (img_path.stem + '.txt')
                if lbl_path.exists():
                    identity_path = self._dataset.get_annotation_identity_path(lbl_path)
                    item.annotations = read_label_file(
                        lbl_path,
                        kpt_shape=kpt_shape,
                        identity_metadata_path=identity_path,
                    )

            if not item.annotations:
                lbl_same = img_path.with_suffix('.txt')
                if lbl_same.exists():
                    identity_path = self._dataset.get_annotation_identity_path(lbl_same)
                    item.annotations = read_label_file(
                        lbl_same,
                        kpt_shape=kpt_shape,
                        identity_metadata_path=identity_path,
                    )

            self._dataset.add_image(item)
            added += 1

        if added > 0:
            self._image_list = self._dataset.get_all_images()
            self.dataset_loaded.emit(self._dataset)

        return added

    # ── Konum yönetimi ──────────────────────────────────────────────────────

    def get_split_positions(self) -> dict:
        """Güncel split bazlı konumları döner (0-bazlı)."""
        return dict(self._split_positions)

    def set_split_positions(self, positions: dict):
        """Kaydedilmiş konumları geri yükler."""
        for k, v in positions.items():
            if k in self._split_positions:
                self._split_positions[k] = int(v)

    def get_split_position_1based(self, split: str) -> int:
        """Belirli bir split için 1-bazlı konum döner (hiç ziyaret edilmemişse 0)."""
        pos = self._split_positions.get(split, -1)
        return pos + 1 if pos >= 0 else 0

    def navigate_to_split_position(self, split: str):
        """Kaydedilmiş split konumuna gider."""
        pos = self._split_positions.get(split, -1)
        if pos < 0:
            return
        if split == "all":
            if pos < len(self._image_list):
                self.load_image_at(pos)
        else:
            split_imgs = [img for img in self._image_list if img.split == split]
            if pos < len(split_imgs):
                try:
                    global_idx = self._image_list.index(split_imgs[pos])
                    self.load_image_at(global_idx)
                except ValueError:
                    pass

    def import_labels_from_folder(self, folder_path: str) -> int:
        """Klasördeki .txt etiket dosyalarını mevcut görsellere stem adıyla eşler ve uygular.

        Returns:
            Etiket uygulanan görsel sayısı
        """
        if not self._dataset:
            return 0

        from pathlib import Path
        from src.io.label_reader import read_label_file

        folder = Path(folder_path)
        if not folder.exists():
            return 0

        kpt_shape = getattr(self._dataset, 'kpt_shape', None)

        # Stem → ImageItem haritası
        stem_to_image = {img.path.stem: img for img in self._image_list}

        applied = 0
        for txt_file in folder.glob("*.txt"):
            img = stem_to_image.get(txt_file.stem)
            if img:
                img.annotations = read_label_file(txt_file, kpt_shape=kpt_shape)
                img.mark_dirty()
                applied += 1

        return applied

    def get_image_list(self):
        return self._image_list

    def get_current_index(self):
        return self._current_index
