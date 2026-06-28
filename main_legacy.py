import logging
import os

import customtkinter as ctk

from src.core.app_config import AppConfig
from src.core.logging_config import configure_logging
from src.ui.main_window import CustomMakerApp


logger = logging.getLogger(__name__)


def main():
    app_config = AppConfig()
    configure_logging(app_config.get("log_level", "INFO"))

    if not os.path.exists(".env"):
        try:
            with open(".env", "w", encoding="utf-8") as f:
                f.write("IMG_CHEST_API_TOKEN=seu_token_aqui\n")
            logger.info(".env criado com template inicial.")
        except OSError:
            logger.warning("Falha ao criar .env automaticamente.")

    appearance_mode = app_config.get("appearance_mode", "Dark")
    ctk.set_appearance_mode(appearance_mode)

    color_theme = app_config.get("color_theme", "blue")
    ctk.set_default_color_theme(color_theme)

    try:
        from tkinterdnd2 import TkinterDnD

        class CTkDnD(ctk.CTk, TkinterDnD.DnDWrapper):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.TkdndVersion = TkinterDnD._require(self)

        root = CTkDnD()
    except ImportError:
        logger.warning("tkinterdnd2 não encontrado. Drag & Drop desativado.")
        root = ctk.CTk()

    CustomMakerApp(root, app_config)
    root.mainloop()


if __name__ == "__main__":
    main()
