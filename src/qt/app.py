import logging
import os

from src.core.app_config import AppConfig
from src.core.logging_config import configure_logging
from src.qt.compat import QT_AVAILABLE, qt_unavailable_error
from src.qt.main_window import QtMainWindow
from src.qt.theme import build_stylesheet, set_active_theme

if QT_AVAILABLE:
    from src.qt.compat import QApplication, QFont


logger = logging.getLogger(__name__)


def install_qt_translations(app):
    """Botões e diálogos padrão do Qt (Sim/Não, Salvar/Cancelar, Fechar,
    seletor de arquivos) em português — sem isto apareciam em inglês no meio
    da interface pt-BR. Se o arquivo de tradução faltar, segue em inglês."""
    from PySide6.QtCore import QLibraryInfo, QTranslator

    translator = QTranslator(app)
    if translator.load("qtbase_pt_BR", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(translator)
        return True
    logger.info("Tradução pt_BR do Qt não encontrada; botões padrão ficam em inglês.")
    return False


def main():
    if not QT_AVAILABLE:
        raise qt_unavailable_error()

    app_config = AppConfig()
    configure_logging(app_config.get("log_level", "INFO"))

    from src.utils.resource_loader import app_data_path
    env_path = app_data_path(".env")
    if not os.path.exists(env_path) and not os.path.exists(".env"):
        try:
            with open(env_path, "w", encoding="utf-8") as file_obj:
                file_obj.write("IMG_CHEST_API_TOKEN=seu_token_aqui\n")
            logger.info(".env criado com template inicial em %s.", env_path)
        except OSError:
            logger.warning("Falha ao criar .env automaticamente.")

    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Custom Maker Pro")
    install_qt_translations(app)
    app.setFont(QFont("Segoe UI", 10))
    # M7: o tema precisa estar ativo antes da janela — widgets leem as cores
    # do tema na construção
    set_active_theme(app_config.get("ui_theme_variant"))
    app.setStyleSheet(build_stylesheet())

    from src.core.session_store import SessionStore
    window = QtMainWindow(app_config, session_store=SessionStore())
    window.show()
    return app.exec()
