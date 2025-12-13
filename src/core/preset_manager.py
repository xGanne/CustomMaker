
import json
import os
from src.config.settings import CONFIG_FILE # Use same dir? Or separate?

# Let's save presets in the same folder as config, processing relative to settings if possible, 
# or just utilize AppConfig logic. But a separate file is cleaner.
# Let's assume standard config location.

PRESETS_FILE = "presets.json"

class PresetManager:
    def __init__(self):
        self.presets = {}
        self.load_presets()

    def load_presets(self):
        if os.path.exists(PRESETS_FILE):
            try:
                with open(PRESETS_FILE, 'r') as f:
                    self.presets = json.load(f)
            except Exception as e:
                print(f"Error loading presets: {e}")
                self.presets = {}
        else:
            self.presets = {}

    def save_presets(self):
        try:
            with open(PRESETS_FILE, 'w') as f:
                json.dump(self.presets, f, indent=4)
        except Exception as e:
            print(f"Error saving presets: {e}")

    def add_preset(self, name, data):
        """
        data: dict containing 'border', 'color_hex', 'anim_type'
        """
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
