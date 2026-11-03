import faulthandler
import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler

from src.utils.resource_loader import app_data_path


DEFAULT_LOG_FILE = app_data_path(os.path.join("logs", "app.log"))
LOG_DIR = os.path.dirname(DEFAULT_LOG_FILE)
CRASH_LOG_NAME = "crash.log"
CRASH_LOG_MAX_BYTES = 1_000_000

logger = logging.getLogger("custommaker")

# arquivo do faulthandler: precisa ficar aberto enquanto o app roda
_crash_file = None


def configure_logging(level_name: str = "INFO", log_file: str = DEFAULT_LOG_FILE) -> None:
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    level = getattr(logging, level_name.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if root_logger.handlers:
        return

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root_logger.addHandler(file_handler)

    # o exe não tem console (sys.stderr é None): só o arquivo
    if sys.stderr is not None:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        root_logger.addHandler(console_handler)


def install_error_logging(log_dir: str = LOG_DIR) -> None:
    """Leva para o log o que antes só aparecia no terminal (ou se perdia no exe).

    - exceções não tratadas, inclusive em slots do Qt e em threads;
    - crash nativo (access violation etc.): `crash.log` via faulthandler.
    """
    global _crash_file
    previous_hook = sys.excepthook

    def excepthook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            previous_hook(exc_type, exc, tb)
            return
        logger.critical("Erro não tratado", exc_info=(exc_type, exc, tb))

    def thread_excepthook(args):
        if args.exc_type is SystemExit:
            return
        name = args.thread.name if args.thread is not None else "?"
        logger.critical("Erro não tratado na thread %s", name,
                        exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook

    if _crash_file is None:
        try:
            os.makedirs(log_dir, exist_ok=True)
            path = os.path.join(log_dir, CRASH_LOG_NAME)
            if os.path.exists(path) and os.path.getsize(path) > CRASH_LOG_MAX_BYTES:
                os.replace(path, path + ".1")
            _crash_file = open(path, "a", encoding="utf-8")
            faulthandler.enable(file=_crash_file, all_threads=True)
        except OSError as exc:
            logger.warning("Sem registro de crash nativo: %s", exc)


def qt_message_handler(mode, context, message):
    """Avisos do próprio Qt (QPainter, QObject...) no log, com o nível certo."""
    from PySide6.QtCore import QtMsgType
    level = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }.get(mode, logging.WARNING)
    logging.getLogger("qt").log(level, "%s", message)
