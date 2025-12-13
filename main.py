import os
import sys
import customtkinter as ctk
from src.ui.main_window import CustomMakerApp
from src.config.settings import CONFIG_FILE
from src.core.app_config import AppConfig

def main():
    # Ensure environment is set up
    if not os.path.exists(".env"):
        try:
            with open(".env", "w") as f:
                f.write("IMG_CHEST_API_TOKEN=seu_token_aqui\n")
            print("INFO: .env criado.")
        except IOError:
            print("AVISO: Falha ao criar .env")

    # Load config and apply theme BEFORE creating window
    app_config = AppConfig()
    
    appearance_mode = app_config.get('appearance_mode', 'Dark')
    ctk.set_appearance_mode(appearance_mode)
    
    color_theme = app_config.get('color_theme', 'blue')
    ctk.set_default_color_theme(color_theme)

    try:
        from tkinterdnd2 import TkinterDnD
        class CTkDnD(ctk.CTk, TkinterDnD.DnDWrapper):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.TkdndVersion = TkinterDnD._require(self)
        root = CTkDnD()
    except ImportError:
        print("AVISO: tkinterdnd2 não encontrado. Drag & Drop desativado.")
        root = ctk.CTk()

    app = CustomMakerApp(root, app_config) # Inject config
    root.mainloop()

if __name__ == "__main__":
    main()
