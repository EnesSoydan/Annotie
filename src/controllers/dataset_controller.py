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
    error_occurred = Signal(str)

    def __init__(self, annotation_controller, main_window, parent=None):
        super().__init__(parent)
        self._ann_ctrl = annotation_controller
        self._window = main_window
        self._dataset = None
        self._current_image = None
        self._image_list = []   # Siradaki gorsel listesi
        self._current_index = -1

    @property
    def dataset(self) -> Dataset:
        return self._dataset

    def open_dataset(self, path: str):
        """YOLO veriseti klasorunu ac."""
        dataset = import_dataset(path)
        if dataset is None:
            self.error_occurred.emit(f"Veriseti acilamadi: {path}")
            return
        self._load_dataset(dataset)

    def open_folder(self, path: str):
        """Duz gorsel klasorunu ac (gecici mod)."""
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
        self.dataset_loaded.emit(dataset)
        self._window.set_dataset(dataset)

        # Ilk gorseli ac
        if self._image_list:
            self.load_image_at(0)

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

        # Gorseli canvas'a yukle
        image.load_dimensions()
        from src.io.image_loader import ImageLoader
        # Image loader olarak basit pixmap yukle
        from PySide6.QtGui import QPixmap
        pixmap = QPixmap(str(image.path))
        if not pixmap.isNull():
            self._ann_ctrl.scene.set_image(pixmap)

        self._ann_ctrl.set_current_image(image)

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
        write_label_file(label_path, image.annotations)
        image.mark_clean()
        self.image_saved.emit(image)

    def set_image_split(self, image, split: str):
        """Gorsel split atamasini degistirir."""
        if image:
            image.split = split

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
                    item.annotations = read_label_file(lbl_path, kpt_shape=kpt_shape)

            if not item.annotations:
                lbl_same = img_path.with_suffix('.txt')
                if lbl_same.exists():
                    item.annotations = read_label_file(lbl_same, kpt_shape=kpt_shape)

            self._dataset.add_image(item)
            added += 1

        if added > 0:
            self._image_list = self._dataset.get_all_images()
            self.dataset_loaded.emit(self._dataset)

        return added

    def get_image_list(self):
        return self._image_list

    def get_current_index(self):
        return self._current_index
