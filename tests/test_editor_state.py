import unittest

from src.core.editor_state import EditorState, UiPreferences


class DummyConfig:
    def __init__(self):
        self.values = {
            "appearance_mode": "Dark",
            "last_folder": "C:/tmp/images",
            "last_global_borda": "Blue",
            "max_workers": 3,
            "image_cache_max_mb": 512,
            "thumbnail_batch_size": 8,
            "thumbnail_batch_interval_ms": 50,
            "thumbnail_memory_cache_mb": 128,
            "thumbnail_disk_cache_mb": 1024,
        }

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


class TestEditorState(unittest.TestCase):
    def test_resolve_border_hex_prefers_individual_custom_color(self):
        state = EditorState(
            selected_borda="White",
            custom_borda_hex="#111111",
            individual_bordas={"a.png": "Cor Personalizada"},
            custom_borda_hex_individual={"a.png": "#222222"},
        )

        resolved = state.resolve_border_hex({"White": "#FFFFFF"}, "a.png")

        self.assertEqual(resolved, "#222222")

    def test_remove_image_updates_current_index(self):
        state = EditorState(image_list=["a.png", "b.png", "c.png"], current_image_index=1)

        state.remove_image("b.png")

        self.assertEqual(state.image_list, ["a.png", "c.png"])
        self.assertEqual(state.current_image_index, 1)
        self.assertEqual(state.current_image_path, "c.png")

    def test_ui_preferences_round_trip_app_config(self):
        cfg = DummyConfig()
        prefs = UiPreferences.from_app_config(cfg)
        prefs.last_global_borda = "Green"
        prefs.save_to_app_config(cfg)

        self.assertEqual(cfg.get("last_global_borda"), "Green")
        self.assertEqual(cfg.get("thumbnail_batch_size"), 8)
