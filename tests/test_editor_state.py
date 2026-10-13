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


class TestUiPreferencesDoNotRevertSettings(unittest.TestCase):
    def test_settings_changed_during_session_survive_save(self):
        """Mudanças feitas em Configurações não são desfeitas ao fechar o app."""
        cfg = DummyConfig()
        prefs = UiPreferences.from_app_config(cfg)
        cfg.set("max_workers", 6)  # diálogo de Configurações, durante a sessão
        cfg.set("image_cache_max_mb", 900)
        cfg.set("thumbnail_disk_cache_mb", 2048)
        prefs.last_folder = "C:/outra"
        prefs.save_to_app_config(cfg)
        self.assertEqual(cfg.get("max_workers"), 6)
        self.assertEqual(cfg.get("image_cache_max_mb"), 900)
        self.assertEqual(cfg.get("thumbnail_disk_cache_mb"), 2048)
        self.assertEqual(cfg.get("last_folder"), "C:/outra")


class TestAutoFraming(unittest.TestCase):
    """Enquadramento automático x ajuste do usuário."""

    def test_auto_state_never_overrides_user_adjustment(self):
        state = EditorState(image_list=["a.png"])
        state.set_image_state("a.png", (5, 5), (100, 150))
        self.assertFalse(state.set_auto_state("a.png", (0, 0), (1, 1)))
        self.assertEqual(state.image_states["a.png"], {"pos": (5, 5), "size": (100, 150)})
        self.assertEqual(state.user_adjusted, {"a.png"})

    def test_auto_state_is_not_dirty_nor_adjusted_until_user_changes_it(self):
        state = EditorState(image_list=["a.png"])
        self.assertTrue(state.set_auto_state("a.png", (0, 0), (225, 350)))
        self.assertEqual(state.image_dirty, set())
        self.assertEqual(state.user_adjusted, set())
        state.set_image_state("a.png", (3, 0), (225, 350))
        self.assertEqual(state.user_adjusted, {"a.png"})
        self.assertEqual(state.image_dirty, {"a.png"})

    def test_remove_and_reset_forget_auto_framing(self):
        state = EditorState(image_list=["a.png", "b.png"])
        state.set_auto_state("a.png", (0, 0), (1, 1))
        state.set_auto_state("b.png", (0, 0), (1, 1))
        state.remove_image("a.png")
        self.assertEqual(state.auto_framed, {"b.png"})
        state.reset_images()
        self.assertEqual(state.auto_framed, set())
