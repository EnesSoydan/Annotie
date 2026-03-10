"""YOLO .txt etiket dosyalarini yazma."""

from pathlib import Path
from typing import List
from src.models.annotation import Annotation


def write_label_file(path: Path, annotations: List[Annotation]) -> bool:
    """Annotation listesini YOLO .txt formatinda yazar.

    Bos liste = bos dosya (etiketlenmis ama nesne yok).
    Atomik yazma: once .tmp dosyasina yazar, sonra rename eder (cokus korumasi).
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix('.tmp')

        lines = []
        for ann in annotations:
            lines.append(ann.to_yolo_line())

        content = '\n'.join(lines)
        if lines:
            content += '\n'

        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # Atomik yeniden adlandirma
        tmp_path.replace(path)
        return True
    except Exception as e:
        print(f"Etiket dosyasi yazilamadi {path}: {e}")
        # Basarisiz tmp dosyasini temizle
        try:
            tmp_path = path.with_suffix('.tmp')
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        return False
