"""Annotie - Giris Noktasi"""

import sys
import traceback
from pathlib import Path

# src klasorunu Python yoluna ekle
sys.path.insert(0, str(Path(__file__).parent))

# Konsol yoksa (EXE modunda) stdout/stderr'i None olmaktan koru. StringIO
# degil devnull: StringIO her print'i bellekte biriktirip sinirsiz buyuyordu.
if sys.stdout is None:
    import os
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    import os
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from src.utils.logging_setup import setup_logging

# Hata log dosyasinin konumu (~/.annotie/logs/annotie.log, donen dosya)
_LOG_PATH = setup_logging()

from src.app import create_application
from src.widgets.main_window import MainWindow

import logging

_logger = logging.getLogger("annotie")
_window_ready = False   # Pencere tam hazir olduktan sonra hata goster


def _write_log(text: str):
    """Hatayi log dosyasina yazar."""
    _logger.error(text)


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

        # Uygulama ikonunu ayarla (pencere + gorev cubugu)
        from PySide6.QtGui import QIcon
        _icon_path = Path(__file__).parent / "icon.ico"
        if not _icon_path.exists():
            # EXE icinde sys._MEIPASS altinda olabilir
            _meipass = getattr(sys, '_MEIPASS', None)
            if _meipass:
                _icon_path = Path(_meipass) / "icon.ico"

        if _icon_path.exists():
            _icon = QIcon(str(_icon_path))
            app.setWindowIcon(_icon)

        # Windows gorev cubugu iconu icin AppUserModelID gerekli
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "annotie.app"
                )
            except Exception:
                pass

        window = MainWindow()

        if _icon_path.exists():
            window.setWindowIcon(_icon)

        window.show()

        # Pencere tamamen gozuktukten sonra hata gostermeye izin ver
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, window.update_manager.check_silently)
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
