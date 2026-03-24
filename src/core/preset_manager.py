import json
import logging
import os


logger = logging.getLogger(__name__)


PRESETS_FILE = "presets.json"


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
        try:
            with open(PRESETS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.presets, f, indent=4, ensure_ascii=False)
        except Exception as exc:
            logger.error("Falha ao salvar presets: %s", exc)

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
