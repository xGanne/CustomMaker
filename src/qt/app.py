import logging
import os

from src.core.app_config import AppConfig
from src.core.logging_config import configure_logging
from src.qt.compat import QT_AVAILABLE, qt_unavailable_error
from src.qt.main_window import QtMainWindow
from src.qt.theme import QT_STYLESHEET

if QT_AVAILABLE:
    from src.qt.compat import QApplication, QFont


logger = logging.getLogger(__name__)


def main():
    if not QT_AVAILABLE:
        raise qt_unavailable_error()

    app_config = AppConfig()
    configure_logging(app_config.get("log_level", "INFO"))

    if not os.path.exists(".env"):
        try:
            with open(".env", "w", encoding="utf-8") as file_obj:
                file_obj.write("IMG_CHEST_API_TOKEN=seu_token_aqui\n")
            logger.info(".env criado com template inicial.")
        except OSError:
            logger.warning("Falha ao criar .env automaticamente.")

    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Custom Maker Pro")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(QT_STYLESHEET)

    window = QtMainWindow(app_config)
    window.show()
    return app.exec()
