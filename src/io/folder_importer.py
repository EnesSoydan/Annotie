"""Klasor import — duz klasor veya YOLO yapisini (images/ + labels/) destekler."""

from pathlib import Path
from typing import Optional, List
from src.models.dataset import Dataset
from src.models.image_item import ImageItem
from src.io.label_reader import read_label_file
from src.utils.constants import SUPPORTED_IMAGE_FORMATS


def import_folder(folder_path: str) -> Optional[Dataset]:
    """Bir klasoru import eder.

    Iki yapıyı otomatik tanır:
    1. YOLO yapisi: secilen klasorde 'images/' alt klasoru varsa,
       gorseller oradan alinir; 'labels/' varsa eslesme yapilir.
       images/ altinda train/val/test alt klasorleri de desteklenir.
    2. Duz klasor: gorsel dosyalari dogrudan klasordedir.
       Gorsel yaninda ayni isimli .txt varsa etiketleri yukler.
    """
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        return None

    dataset = Dataset(root_path=folder, is_temporary=True)

    images_dir = folder / "images"
    labels_dir = folder / "labels"

    if images_dir.exists() and images_dir.is_dir():
        # YOLO yapisi: images/ (ve opsiyonel labels/) alt klasoru var
        _import_yolo_structure(dataset, images_dir, labels_dir)
    else:
        # Duz klasor yapisi
        _import_flat_folder(dataset, folder)

    return dataset


def _import_yolo_structure(dataset: Dataset, images_dir: Path, labels_dir: Path):
    """YOLO images/labels yapisinden gorselleri import eder."""
    # images/ icinde dogrudan gorseller mi var, yoksa train/val/test alt klasorleri mi?
    direct_images = _collect_images_in_dir(images_dir)

    if direct_images:
        # images/ icinde dogrudan gorseller var (split yok)
        for img_path in direct_images:
            item = ImageItem(path=img_path, split="unassigned")
            _try_load_label(item, img_path, labels_dir)
            dataset.add_image(item)
    else:
        # images/ altinda split klasorleri olabilir: train/, val/, test/
        for split_dir in sorted(images_dir.iterdir()):
            if not split_dir.is_dir():
                continue
            split = _detect_split_from_name(split_dir.name)
            split_labels = labels_dir / split_dir.name if labels_dir.exists() else None
            for img_path in _collect_images_in_dir(split_dir):
                item = ImageItem(path=img_path, split=split)
                _try_load_label(item, img_path, split_labels)
                dataset.add_image(item)


def _import_flat_folder(dataset: Dataset, folder: Path):
    """Duz klasor yapisından gorselleri import eder (recursive)."""
    for img_path in _collect_images_recursive(folder):
        item = ImageItem(path=img_path, split="unassigned")
        lbl_path = img_path.with_suffix('.txt')
        if lbl_path.exists():
            item.annotations = read_label_file(lbl_path)
        dataset.add_image(item)


def _try_load_label(item: ImageItem, img_path: Path, lbl_dir):
    """Gorsel icin etiketi bulmaya calisir."""
    # 1) labels/ klasorundan ara
    if not item.annotations and lbl_dir and Path(lbl_dir).exists():
        lbl_path = Path(lbl_dir) / (img_path.stem + '.txt')
        if lbl_path.exists():
            item.annotations = read_label_file(lbl_path)

    # 2) Yedek: gorsel yaniında .txt
    if not item.annotations:
        lbl_same = img_path.with_suffix('.txt')
        if lbl_same.exists():
            item.annotations = read_label_file(lbl_same)


def _detect_split_from_name(name: str) -> str:
    """Klasor ismine gore split belirler."""
    n = name.lower()
    if "train" in n:
        return "train"
    elif "val" in n or "valid" in n:
        return "val"
    elif "test" in n:
        return "test"
    return "unassigned"


def _collect_images_in_dir(directory: Path) -> List[Path]:
    """Bir klasordeki (alt klasorler haric) gorsel dosyalarini toplar."""
    images = []
    for ext in SUPPORTED_IMAGE_FORMATS:
        images.extend(directory.glob(f'*{ext}'))
        images.extend(directory.glob(f'*{ext.upper()}'))
    return sorted(set(images))


def _collect_images_recursive(directory: Path) -> List[Path]:
    """Alt klasorler dahil tum desteklenen gorselleri toplar."""
    images = []
    for ext in SUPPORTED_IMAGE_FORMATS:
        images.extend(directory.rglob(f'*{ext}'))
        images.extend(directory.rglob(f'*{ext.upper()}'))
    return sorted(set(images))
