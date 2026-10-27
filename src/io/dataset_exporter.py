"""YOLO formatinda veriseti export etme."""

import dataclasses
from pathlib import Path
from typing import List, Optional, Set
import shutil
from src.models.dataset import Dataset
from src.io.label_reader import read_label_file
from src.io.label_writer import write_label_file
from src.io.annotation_identity import identity_metadata_path
from src.io.yaml_handler import write_data_yaml


def _annotations_for_export(img) -> List:
    """Gorselin etiketleri; editorde hic acilmamis (lazy) gorseller diskten okunur.

    load_pending_labels() cagrilmaz: export worker thread'inde calisir ve
    ImageItem'i UI thread'inden habersiz degistirmemelidir.
    """
    pending = getattr(img, "_pending_label_path", None)
    if pending is not None:
        return read_label_file(
            pending,
            kpt_shape=getattr(img, "_pending_kpt_shape", None),
            identity_metadata_path=getattr(img, "_pending_identity_path", None),
        )
    return list(img.annotations)


def _unique_stem(stem: str, used: Set[str]) -> str:
    """Ayni split'e ayni adla dusen gorseller (a.jpg + a.png de ayni a.txt'yi
    paylasir) birbirinin uzerine yazmasin."""
    candidate = stem
    n = 1
    while candidate.lower() in used:
        candidate = f"{stem}_{n}"
        n += 1
    used.add(candidate.lower())
    return candidate


def export_dataset(dataset: Dataset, export_path: str, copy_images: bool = True,
                   progress_callback=None, cancel_check=None) -> bool:
    """Veriseti YOLO formatinda export eder.

    Klasor yapisi:
    export_path/
      train/images/   train/labels/
      valid/images/   valid/labels/
      test/images/    test/labels/
      data.yaml
    """
    try:
        root = Path(export_path)
        root.mkdir(parents=True, exist_ok=True)

        # Dahili split adi → klasor adi eslemesi
        # (model 'val' kullanir, disk'te 'valid' klasoru olusturulur)
        SPLIT_FOLDER = {'train': 'train', 'val': 'valid', 'test': 'test'}

        # Klasor yapisi olustur
        for folder in SPLIT_FOLDER.values():
            (root / folder / 'images').mkdir(parents=True, exist_ok=True)
            (root / folder / 'labels').mkdir(parents=True, exist_ok=True)

        # Gorselleri ve etiketleri yaz
        images = dataset.get_all_images()
        total = len(images)
        used_names = {folder: set() for folder in SPLIT_FOLDER.values()}
        for idx, img in enumerate(images):
            split = img.split if img.split in SPLIT_FOLDER else 'train'
            folder = SPLIT_FOLDER[split]
            stem = _unique_stem(img.stem, used_names[folder])
            img_dst = root / folder / 'images' / f"{stem}{img.path.suffix}"
            lbl_dst = root / folder / 'labels' / f"{stem}.txt"

            if cancel_check and cancel_check():
                return False

            if copy_images and img.path.exists():
                shutil.copy2(img.path, img_dst)

            metadata_path = identity_metadata_path(root, lbl_dst)
            if not write_label_file(lbl_dst, _annotations_for_export(img), metadata_path):
                return False

            if progress_callback:
                progress_callback(idx + 1, total)

        # data.yaml, export klasorunu gosteren bir KOPYA ile yazilir; acik
        # dataset'in yollari degismez (sonraki kayitlar yerinde kalir).
        exported = dataclasses.replace(
            dataset,
            root_path=root,
            train_images_path=root / 'train' / 'images',
            val_images_path=root / 'valid' / 'images',
            test_images_path=root / 'test' / 'images',
            train_labels_path=root / 'train' / 'labels',
            val_labels_path=root / 'valid' / 'labels',
            test_labels_path=root / 'test' / 'labels',
        )
        write_data_yaml(root / 'data.yaml', exported)

        return True
    except Exception as e:
        print(f"Export hatasi: {e}")
        return False


def create_dataset_structure(root_path: str, dataset: Dataset) -> bool:
    """Bos YOLO veriseti klasor yapisini olusturur."""
    try:
        root = Path(root_path)
        for folder in ('train', 'valid', 'test'):
            (root / folder / 'images').mkdir(parents=True, exist_ok=True)
            (root / folder / 'labels').mkdir(parents=True, exist_ok=True)

        dataset.root_path = root
        dataset.train_images_path = root / 'train' / 'images'
        dataset.val_images_path = root / 'valid' / 'images'
        dataset.test_images_path = root / 'test' / 'images'
        dataset.train_labels_path = root / 'train' / 'labels'
        dataset.val_labels_path = root / 'valid' / 'labels'
        dataset.test_labels_path = root / 'test' / 'labels'

        write_data_yaml(root / 'data.yaml', dataset)
        return True
    except Exception as e:
        print(f"Veriseti yapisi olusturulamadi: {e}")
        return False
