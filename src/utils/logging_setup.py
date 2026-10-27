"""Uygulama genelinde loglama: dönen log dosyası + çökme izleri.

Loglar ~/.annotie/logs/annotie.log (2 MB x 5 dosya) dosyasına yazılır.
Yerel (native) çökmeler (ör. onnxruntime, Qt) faulthandler ile crash.log'a,
iş parçacığı ve Qt uyarıları da aynı log'a düşer. ANNOTIE_DEBUG=1 ile
ayrıntılı (DEBUG) loglar açılır.
"""

from __future__ import annotations

import faulthandler
import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path.home() / ".annotie" / "logs"
LOG_FILE = LOG_DIR / "annotie.log"
CRASH_FILE = LOG_DIR / "crash.log"

_crash_stream = None  # faulthandler dosyası süreç boyunca açık kalmalı


def setup_logging() -> Path:
    """Kök logger'ı yapılandırır ve log dosyasının yolunu döndürür."""
    global _crash_stream
    level = logging.DEBUG if os.environ.get("ANNOTIE_DEBUG") == "1" else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return LOG_FILE

    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        handler = RotatingFileHandler(LOG_FILE, maxBytes=2 * 1024 * 1024,
                                      backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s"))
        root.addHandler(handler)

    # Paketlenmiş uygulamada konsol yok; geliştirmede konsola da yaz
    if not getattr(sys, "frozen", False) and sys.stderr is not None:
        if not any(type(h) is logging.StreamHandler for h in root.handlers):
            console = logging.StreamHandler()
            console.setLevel(logging.WARNING)
            console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
            root.addHandler(console)

    if _crash_stream is None:
        try:
            _crash_stream = open(CRASH_FILE, "a", encoding="utf-8")
            faulthandler.enable(file=_crash_stream)
        except (OSError, RuntimeError):
            _crash_stream = None

    def _thread_hook(args):
        if issubclass(args.exc_type, SystemExit):
            return
        logging.getLogger("annotie.thread").error(
            "Yakalanmamış hata (%s)", getattr(args.thread, "name", "?"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    threading.excepthook = _thread_hook
    _install_qt_handler()
    return LOG_FILE


def _install_qt_handler():
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except Exception:
        return
    qt_logger = logging.getLogger("annotie.qt")
    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def _handler(mode, _context, message):
        qt_logger.log(levels.get(mode, logging.WARNING), message)

    qInstallMessageHandler(_handler)
