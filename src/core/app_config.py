import os
import json
from src.config.settings import CONFIG_FILE

class AppConfig:
    def __init__(self):
        self.config_data = {
            'last_folder': None,
            'last_global_borda': 'White'
        }
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    loaded = json.load(f)
                    self.config_data.update(loaded)
            except json.JSONDecodeError:
                print(f"AVISO: Erro ao ler {CONFIG_FILE}. Usando padrão.")
    
    def save(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config_data, f, indent=4)
        except IOError as e:
            print(f"ERRO: Não foi possível salvar config: {e}")

    def get(self, key, default=None):
        return self.config_data.get(key, default)

    def set(self, key, value):
        self.config_data[key] = value
        # Optional: auto-save on set? Or manual save.
        # Let's keep manual save to avoid IO spam, or save on important changes.
