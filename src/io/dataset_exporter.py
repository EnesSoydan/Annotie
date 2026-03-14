"""YOLO formatinda veriseti export etme."""

from pathlib import Path
from typing import Optional
import shutil
from src.models.dataset import Dataset
from src.io.label_writer import write_label_file
from src.io.yaml_handler import write_data_yaml


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
        for idx, img in enumerate(images):
            split = img.split if img.split in SPLIT_FOLDER else 'train'
            folder = SPLIT_FOLDER[split]
            img_dst = root / folder / 'images' / img.filename
            lbl_dst = root / folder / 'labels' / img.label_filename

            if cancel_check and cancel_check():
                return False

            if copy_images and img.path.exists():
                shutil.copy2(img.path, img_dst)

            write_label_file(lbl_dst, img.annotations)

            if progress_callback:
                progress_callback(idx + 1, total)

        # Dataset yollarini guncelle (yaml icin)
        dataset.root_path = root
        dataset.train_images_path = root / 'train' / 'images'
        dataset.val_images_path = root / 'valid' / 'images'
        dataset.test_images_path = root / 'test' / 'images'
        dataset.train_labels_path = root / 'train' / 'labels'
        dataset.val_labels_path = root / 'valid' / 'labels'
        dataset.test_labels_path = root / 'test' / 'labels'

        # data.yaml yaz
        write_data_yaml(root / 'data.yaml', dataset)

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
