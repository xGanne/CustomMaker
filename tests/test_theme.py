import json
import tempfile
import unittest
from unittest.mock import patch

from src.config.settings import DEFAULT_THEME_VARIANT, THEME_LABELS, UI_THEMES


def _luminance(hex_color):
    hex_color = hex_color.lstrip("#")
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class TestThemeTokens(unittest.TestCase):
    """M7: os temas são intercambiáveis e legíveis."""

    def test_all_themes_define_the_same_tokens(self):
        reference = set(UI_THEMES[DEFAULT_THEME_VARIANT])
        for variant, theme_tokens in UI_THEMES.items():
            self.assertEqual(set(theme_tokens), reference, variant)

    def test_every_theme_has_a_label(self):
        self.assertEqual(set(THEME_LABELS), set(UI_THEMES))

    def test_text_contrast_meets_wcag_aa(self):
        for variant, t in UI_THEMES.items():
            for surface in ("surface_bg", "surface_panel"):
                for text in ("text_primary", "text_secondary", "text_muted"):
                    with self.subTest(variant=variant, text=text, surface=surface):
                        self.assertGreaterEqual(contrast(t[text], t[surface]), 4.5)
            with self.subTest(variant=variant, text="on_accent"):
                # botões primários: texto curto e em negrito (WCAG AA para texto grande)
                self.assertGreaterEqual(contrast(t["on_accent"], t["accent"]), 3.0)


class TestThemeModule(unittest.TestCase):
    def tearDown(self):
        from src.qt import theme
        theme.set_active_theme(DEFAULT_THEME_VARIANT)

    def test_unknown_variant_falls_back_to_default(self):
        from src.qt import theme
        self.assertEqual(theme.set_active_theme("neon_v9"), DEFAULT_THEME_VARIANT)

    def test_tokens_follow_active_theme(self):
        from src.qt import theme
        theme.set_active_theme("editorial_light_v1")
        self.assertEqual(theme.tokens(), UI_THEMES["editorial_light_v1"])

    def test_stylesheet_uses_theme_colors(self):
        from src.qt import theme
        light = theme.build_stylesheet("editorial_light_v1")
        dark = theme.build_stylesheet("editorial_dark_v1")
        self.assertIn(UI_THEMES["editorial_light_v1"]["surface_bg"], light)
        self.assertNotIn(UI_THEMES["editorial_light_v1"]["surface_bg"], dark)
        self.assertIn("chevron-down-editorial_light_v1.svg", light)


class TestThemeConfig(unittest.TestCase):
    def _load(self, data):
        from src.core.app_config import AppConfig
        with tempfile.TemporaryDirectory() as tmp:
            config_path = f"{tmp}/custommaker_config.json"
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            with patch("src.core.app_config.CONFIG_FILE", config_path):
                return AppConfig()

    def test_light_theme_is_accepted(self):
        self.assertEqual(self._load({"ui_theme_variant": "editorial_light_v1"}).get("ui_theme_variant"),
                         "editorial_light_v1")

    def test_unknown_theme_resets_to_default(self):
        self.assertEqual(self._load({"ui_theme_variant": "rosa"}).get("ui_theme_variant"), DEFAULT_THEME_VARIANT)


if __name__ == "__main__":
    unittest.main()
