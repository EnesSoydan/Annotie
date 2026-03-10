"""YOLO veriseti klasor yapisini otomatik algilayarak import etme."""

from pathlib import Path
from typing import Optional, List, Tuple
from src.models.dataset import Dataset
from src.models.image_item import ImageItem
from src.models.label_class import LabelClass
from src.models.annotation import AnnotationType
from src.io.yaml_handler import read_data_yaml, parse_class_names
from src.io.label_reader import read_label_file
from src.utils.constants import SUPPORTED_IMAGE_FORMATS, YAML_FILENAME


def import_dataset(root_path: str) -> Optional[Dataset]:
    """YOLO veriseti klasorunu import eder."""
    root = Path(root_path)
    if not root.exists():
        return None

    dataset = Dataset(root_path=root)

    # data.yaml bul ve oku
    yaml_path = root / YAML_FILENAME
    yaml_data = None
    if yaml_path.exists():
        yaml_data = read_data_yaml(yaml_path)

    # Sinif isimlerini yukle
    if yaml_data:
        names = parse_class_names(yaml_data)
        for i, name in enumerate(names):
            lc = LabelClass(id=i, name=name)
            dataset.classes.append(lc)

        # kpt_shape
        if 'kpt_shape' in yaml_data:
            kpt = yaml_data['kpt_shape']
            if isinstance(kpt, (list, tuple)) and len(kpt) == 2:
                dataset.kpt_shape = tuple(kpt)

    # Klasor yapisi: iki olasi yapi desteklenir
    # 1) images/train  labels/train  (Ultralytics standardi)
    # 2) train/images  train/labels  (eski format)
    _detect_and_set_paths(root, yaml_data, dataset)

    # Gorselleri yukle
    splits = [
        ("train", dataset.train_images_path, dataset.train_labels_path),
        ("val",   dataset.val_images_path,   dataset.val_labels_path),
        ("test",  dataset.test_images_path,  dataset.test_labels_path),
    ]

    kpt_shape = dataset.kpt_shape

    for split, img_dir, lbl_dir in splits:
        if img_dir is None or not img_dir.exists():
            continue
        images = _collect_images(img_dir)
        for img_path in images:
            item = ImageItem(path=img_path, split=split)
            # Karsilik gelen etiket dosyasini bul
            if lbl_dir and lbl_dir.exists():
                lbl_path = lbl_dir / (img_path.stem + '.txt')
                if lbl_path.exists():
                    item.annotations = read_label_file(lbl_path, kpt_shape=kpt_shape)
            dataset.add_image(item)

    # Fallback: split yapisi bulunamazsa (data.yaml yok veya klasor yapisi farkli),
    # images/ klasorunu veya root klasorunu tara
    if not dataset.images:
        images_dir = root / 'images'
        labels_dir = root / 'labels'
        if images_dir.exists() and images_dir.is_dir():
            # images/ alt klasoru var ama split yapisi yok → direkt tara
            for img_path in _collect_images(images_dir):
                item = ImageItem(path=img_path, split='unassigned')
                if labels_dir.exists():
                    lbl_path = labels_dir / (img_path.stem + '.txt')
                    if lbl_path.exists():
                        item.annotations = read_label_file(lbl_path, kpt_shape=kpt_shape)
                dataset.add_image(item)
        else:
            # Duz klasor: root'taki gorselleri yukle
            for img_path in _collect_images(root):
                item = ImageItem(path=img_path, split='unassigned')
                lbl_same = img_path.with_suffix('.txt')
                if lbl_same.exists():
                    item.annotations = read_label_file(lbl_same, kpt_shape=kpt_shape)
                dataset.add_image(item)

    return dataset


def _detect_and_set_paths(root: Path, yaml_data, dataset: Dataset):
    """Veriseti yollarini otomatik algilar."""

    def resolve(rel: str) -> Optional[Path]:
        if not rel:
            return None
        p = Path(rel)
        if p.is_absolute():
            return p if p.exists() else None
        # Relative to root
        candidate = root / p
        if candidate.exists():
            return candidate
        return None

    if yaml_data:
        train_rel = yaml_data.get('train', '')
        val_rel = yaml_data.get('val', yaml_data.get('valid', ''))
        test_rel = yaml_data.get('test', '')

        train_img = resolve(train_rel)
        val_img = resolve(val_rel)
        test_img = resolve(test_rel)
    else:
        train_img = val_img = test_img = None

    # Yoksa standart yollari dene
    if train_img is None:
        for candidate in [root / 'images' / 'train', root / 'train' / 'images']:
            if candidate.exists():
                train_img = candidate
                break

    if val_img is None:
        for candidate in [root / 'images' / 'val', root / 'valid' / 'images',
                          root / 'images' / 'valid', root / 'val' / 'images']:
            if candidate.exists():
                val_img = candidate
                break

    if test_img is None:
        for candidate in [root / 'images' / 'test', root / 'test' / 'images']:
            if candidate.exists():
                test_img = candidate
                break

    dataset.train_images_path = train_img
    dataset.val_images_path = val_img
    dataset.test_images_path = test_img

    # Etiket yollarini images'ten labels'a esle
    if train_img:
        dataset.train_labels_path = _images_to_labels(train_img)
    if val_img:
        dataset.val_labels_path = _images_to_labels(val_img)
    if test_img:
        dataset.test_labels_path = _images_to_labels(test_img)


def _images_to_labels(images_path: Path) -> Optional[Path]:
    """images klasoru yolunu labels yoluna cevirir."""
    parts = images_path.parts
    new_parts = []
    replaced = False
    for part in parts:
        if part == 'images' and not replaced:
            new_parts.append('labels')
            replaced = True
        else:
            new_parts.append(part)
    if not replaced:
        return None
    return Path(*new_parts) if len(new_parts) > 1 else Path(new_parts[0])


def _collect_images(directory: Path) -> List[Path]:
    """Bir klasordeki tum desteklenen gorsel dosyalarini toplar."""
    images = []
    for ext in SUPPORTED_IMAGE_FORMATS:
        images.extend(directory.glob(f'*{ext}'))
        images.extend(directory.glob(f'*{ext.upper()}'))
    return sorted(set(images))
