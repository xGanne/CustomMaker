import faulthandler
import logging
import os
import sys
import threading
import unittest
from tempfile import TemporaryDirectory

from src.core import logging_config


class TestErrorLogging(unittest.TestCase):
    """Erros não tratados e crash nativo chegam ao log (o exe não tem console)."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        hooks = (sys.excepthook, threading.excepthook)

        def restore():
            sys.excepthook, threading.excepthook = hooks
            faulthandler.disable()
            if sys.stderr is not None:
                faulthandler.enable()  # como o pytest deixa
            if logging_config._crash_file is not None:
                logging_config._crash_file.close()
                logging_config._crash_file = None

        self.addCleanup(restore)
        self.records = []
        handler = logging.Handler(level=logging.DEBUG)
        handler.emit = self.records.append
        for name in ("custommaker", "qt"):
            log = logging.getLogger(name)
            log.addHandler(handler)
            self.addCleanup(log.removeHandler, handler)
        logging_config.install_error_logging(self.tmp.name)

    def test_unhandled_exception_goes_to_the_log_with_traceback(self):
        try:
            raise ValueError("falhou no slot")
        except ValueError:
            sys.excepthook(*sys.exc_info())
        record = self.records[-1]
        self.assertEqual(record.levelno, logging.CRITICAL)
        self.assertIn("falhou no slot", logging.Formatter().format(record))

    def test_thread_exception_goes_to_the_log(self):
        thread = threading.Thread(target=lambda: 1 / 0, name="worker-x")
        thread.start()
        thread.join()
        self.assertTrue(any("worker-x" in r.getMessage() for r in self.records), self.records)

    def test_native_crash_log_is_open(self):
        self.assertTrue(faulthandler.is_enabled())
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, logging_config.CRASH_LOG_NAME)))

    def test_qt_messages_keep_their_level(self):
        from PySide6.QtCore import QtMsgType
        logging_config.qt_message_handler(QtMsgType.QtWarningMsg, None, "QPainter::begin: nada")
        self.assertEqual((self.records[-1].levelno, self.records[-1].getMessage()),
                         (logging.WARNING, "QPainter::begin: nada"))


if __name__ == "__main__":
    unittest.main()
