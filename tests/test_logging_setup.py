"""Loglama kurulumu: dönen dosya, iş parçacığı hataları."""

import faulthandler
import logging
import tempfile
import threading
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest import mock

from src.utils import logging_setup


class LoggingSetupTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self._root = logging.getLogger()
        self._saved = (list(self._root.handlers), self._root.level, threading.excepthook)
        patches = [
            mock.patch.object(logging_setup, "LOG_DIR", tmp),
            mock.patch.object(logging_setup, "LOG_FILE", tmp / "annotie.log"),
            mock.patch.object(logging_setup, "CRASH_FILE", tmp / "crash.log"),
            mock.patch.object(logging_setup, "_crash_stream", None),
            mock.patch.object(logging_setup, "_install_qt_handler", lambda: None),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        handlers, level, hook = self._saved
        for h in list(self._root.handlers):
            if h not in handlers:
                self._root.removeHandler(h)
                h.close()
        self._root.setLevel(level)
        threading.excepthook = hook
        faulthandler.disable()
        if logging_setup._crash_stream:
            logging_setup._crash_stream.close()
        self._tmp.cleanup()

    def test_thread_exceptions_reach_rotating_log(self):
        path = logging_setup.setup_logging()
        self.assertTrue(any(isinstance(h, RotatingFileHandler) for h in self._root.handlers))

        def boom():
            raise ValueError("arka plan hatasi")

        t = threading.Thread(target=boom, name="IsciThread")
        t.start()
        t.join()
        for h in self._root.handlers:
            h.flush()
        text = path.read_text(encoding="utf-8")
        self.assertIn("arka plan hatasi", text)
        self.assertIn("IsciThread", text)

    def test_setup_is_idempotent(self):
        logging_setup.setup_logging()
        logging_setup.setup_logging()
        count = sum(isinstance(h, RotatingFileHandler) for h in self._root.handlers)
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
