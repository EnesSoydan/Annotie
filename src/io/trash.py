"""Silinen görsel/etiket dosyaları için kalıcı çöp kutusu.

Görsel silme kısayolu (Del) dosyayı diskten kaldırır; yanlışlıkla silinenler
uygulamanın kısa geri-al süresinden sonra da kurtarılabilsin diye dosyalar
önce ~/.annotie/trash/<zaman>/ altına, orijinal tam yolları korunarak kopyalanır.
Dataset klasörünün dışında tutulur: içe aktarma taramaları (rglob) çöpteki
görselleri yeniden datasete eklemesin.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Iterable, Optional

TRASH_ROOT = Path.home() / ".annotie" / "trash"


def _relative_for_trash(path: Path) -> Path:
    """C:\\veri\\a.jpg → C/veri/a.jpg ; /home/u/a.jpg → home/u/a.jpg"""
    path = Path(path).resolve()
    drive = path.drive.rstrip(":").replace("\\", "_").replace("/", "_")
    parts = path.parts[1:]
    return Path(drive, *parts) if drive else Path(*parts)


def copy_to_trash(paths: Iterable[Path], trash_root: Optional[Path] = None) -> Path:
    """Var olan dosyaları yeni bir çöp klasörüne kopyalar ve klasörü döndürür.

    Kopyalanamayan bir dosya olursa OSError fırlatır; çağıran silmeyi iptal etmeli.
    """
    root = trash_root or TRASH_ROOT
    batch = root / time.strftime("%Y%m%d-%H%M%S")
    n = 1
    while batch.exists():
        batch = root / f"{time.strftime('%Y%m%d-%H%M%S')}-{n}"
        n += 1
    for path in paths:
        path = Path(path)
        if not path.is_file():
            continue
        target = batch / _relative_for_trash(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return batch
