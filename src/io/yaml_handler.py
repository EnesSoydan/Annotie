"""data.yaml dosyasi okuma ve yazma."""

from pathlib import Path
from typing import Optional, Dict, Any
import yaml


def read_data_yaml(path: Path) -> Optional[Dict[str, Any]]:
    """data.yaml dosyasini okur ve icerik sozlugunu dondurur."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return None
        return data
    except Exception as e:
        print(f"data.yaml okunamadi: {e}")
        return None


def parse_class_names(data: Dict[str, Any]) -> list:
    """data.yaml'dan sinif isimlerini ceker. Hem dict hem list formatini destekler."""
    names = data.get('names', [])
    if isinstance(names, dict):
        # {0: 'cat', 1: 'dog'} formati
        max_id = max(names.keys()) if names else -1
        result = [''] * (max_id + 1)
        for k, v in names.items():
            result[int(k)] = str(v)
        return result
    elif isinstance(names, list):
        return [str(n) for n in names]
    return []


def write_data_yaml(path: Path, dataset) -> bool:
    """Dataset modelinden data.yaml yazar."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}

        if dataset.root_path:
            data['path'] = str(dataset.root_path)

        if dataset.train_images_path and dataset.root_path:
            try:
                rel = dataset.train_images_path.relative_to(dataset.root_path)
                data['train'] = './' + rel.as_posix()
            except ValueError:
                data['train'] = dataset.train_images_path.as_posix()

        if dataset.val_images_path and dataset.root_path:
            try:
                rel = dataset.val_images_path.relative_to(dataset.root_path)
                data['val'] = './' + rel.as_posix()
            except ValueError:
                data['val'] = dataset.val_images_path.as_posix()

        if dataset.test_images_path and dataset.root_path:
            try:
                rel = dataset.test_images_path.relative_to(dataset.root_path)
                data['test'] = './' + rel.as_posix()
            except ValueError:
                data['test'] = dataset.test_images_path.as_posix()

        data['nc'] = dataset.class_count
        data['names'] = {c.id: c.name for c in dataset.classes}

        if dataset.kpt_shape:
            data['kpt_shape'] = list(dataset.kpt_shape)

        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        return True
    except Exception as e:
        print(f"data.yaml yazilamadi: {e}")
        return False
