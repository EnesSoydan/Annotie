"""QApplication olusturma ve yapilandirma."""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QImageReader
from src.utils.constants import APP_NAME, APP_VERSION, ORG_NAME


def create_application(argv=None) -> QApplication:
    """Uygulamayi olusturur ve yapilandirir."""
    if argv is None:
        argv = sys.argv

    # Qt varsayilan 256 MB sinirini kaldir; yuksek cozunurluklu (>11kx8k) gorseller icin gerekli
    QImageReader.setAllocationLimit(0)

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationVersion(APP_VERSION)

    # Yuksek DPI destegi
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Varsayilan font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    return app
