import json
import logging
import os

from src.utils.resource_loader import app_data_path


logger = logging.getLogger(__name__)


PRESETS_FILE = app_data_path("presets.json")


class PresetManager:
    def __init__(self):
        self.presets = {}
        self.load_presets()

    def load_presets(self):
        if not os.path.exists(PRESETS_FILE):
            self.presets = {}
            return
        try:
            with open(PRESETS_FILE, "r", encoding="utf-8") as f:
                self.presets = json.load(f)
        except Exception as exc:
            logger.warning("Falha ao carregar presets: %s", exc)
            self.presets = {}

    def save_presets(self):
        # F14: escrita atômica — um crash no meio do dump não corrompe o arquivo
        tmp_path = f"{PRESETS_FILE}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.presets, f, indent=4, ensure_ascii=False)
            os.replace(tmp_path, PRESETS_FILE)
        except Exception as exc:
            logger.error("Falha ao salvar presets: %s", exc)
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def add_preset(self, name, data):
        self.presets[name] = data
        self.save_presets()

    def get_preset(self, name):
        return self.presets.get(name)

    def delete_preset(self, name):
        if name in self.presets:
            del self.presets[name]
            self.save_presets()
            return True
        return False

    def list_presets(self):
        return list(self.presets.keys())

    @staticmethod
    def swatch_color(data, borda_hex):
        """M11: cor exibida ao lado do nome do preset no combo."""
        if not isinstance(data, dict):
            return None
        border_name = data.get("border_name")
        if border_name == "Cor Personalizada":
            color = data.get("border_color")
            if isinstance(color, str) and color.startswith("#") and len(color) == 7:
                return color
            return None
        return borda_hex.get(border_name)
