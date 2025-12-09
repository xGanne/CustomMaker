import os
import sys
import customtkinter as ctk
from src.ui.main_window import CustomMakerApp
from src.config.settings import CONFIG_FILE

def main():
    # Ensure environment is set up
    if not os.path.exists(".env"):
        try:
            with open(".env", "w") as f:
                f.write("IMG_CHEST_API_TOKEN=seu_token_aqui\n")
            print("INFO: .env criado.")
        except IOError:
            print("AVISO: Falha ao criar .env")

    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    app = CustomMakerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
