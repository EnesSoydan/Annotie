"""Annotie - Giris Noktasi"""

import sys
import traceback
from pathlib import Path

# src klasorunu Python yoluna ekle
sys.path.insert(0, str(Path(__file__).parent))

# Konsol yoksa (EXE modunda) stdout/stderr'i None olmaktan koru
if sys.stdout is None:
    import io
    sys.stdout = io.StringIO()
if sys.stderr is None:
    import io
    sys.stderr = io.StringIO()

from src.app import create_application
from src.widgets.main_window import MainWindow


# Hata log dosyasinin konumu
_LOG_PATH = Path.home() / "Annotie_errors.log"
_window_ready = False   # Pencere tam hazir olduktan sonra hata goster


def _write_log(text: str):
    """Hatay log dosyasina yazar."""
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            from datetime import datetime
            f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{text}\n")
    except Exception:
        pass


def exception_hook(exc_type, exc_value, exc_tb):
    """Yakalanmamis hatalari yakalar, loglar ve (pencere hazirsa) gosterir."""
    # KeyboardInterrupt'i sessizce gecir
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    tb_str = ""
    try:
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    except Exception:
        tb_str = str(exc_value)

    # Her zaman log dosyasina yaz
    _write_log(tb_str)

    # Guvenli stderr cikisi
    try:
        print(f"Hata:\n{tb_str}", file=sys.stderr)
    except Exception:
        pass

    # Pencere tamamen acilmadan once hata dialog'u gosterme
    # (EXE baslangicinda PyInstaller'in neden oldugu yanltici hatalari gizler)
    if not _window_ready:
        return

    try:
        from PySide6.QtWidgets import QMessageBox, QApplication
        if QApplication.instance():
            QMessageBox.critical(
                None, "Hata",
                f"Beklenmeyen bir hata olustu:\n\n{exc_value}\n\n"
                f"Detaylar su dosyada:\n{_LOG_PATH}"
            )
    except Exception:
        pass


def main():
    global _window_ready
    sys.excepthook = exception_hook

    try:
        app = create_application(sys.argv)
        window = MainWindow()
        window.show()

        # Pencere tamamen gozuktukten sonra hata gostermeye izin ver
        from PySide6.QtCore import QTimer
        def _mark_ready():
            global _window_ready
            _window_ready = True
        QTimer.singleShot(500, _mark_ready)
        QTimer.singleShot(100, window.canvas_view.zoom_fit)

        sys.exit(app.exec())

    except Exception as e:
        tb = traceback.format_exc()
        _write_log(tb)
        try:
            from PySide6.QtWidgets import QMessageBox, QApplication
            if QApplication.instance():
                QMessageBox.critical(
                    None, "Baslatma Hatasi",
                    f"Uygulama baslatilirken hata olustu:\n\n{e}\n\n"
                    f"Detaylar: {_LOG_PATH}"
                )
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
