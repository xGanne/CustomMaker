import json
import tempfile
import unittest
from unittest.mock import patch

from src.core.app_config import AppConfig, CURRENT_CONFIG_VERSION, DEFAULT_CONFIG


class TestAppConfig(unittest.TestCase):
    def test_load_migrates_legacy_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = f"{tmp}/custommaker_config.json"
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "last_folder": "C:/tmp/images",
                        "last_global_borda": "Blue",
                        "feature_flags": ["invalid"],
                    },
                    f,
                )

            with patch("src.core.app_config.CONFIG_FILE", config_path):
                cfg = AppConfig()

            self.assertEqual(cfg.get("config_version"), CURRENT_CONFIG_VERSION)
            self.assertEqual(cfg.get("last_folder"), "C:/tmp/images")
            self.assertEqual(cfg.get("feature_flags"), {})
            self.assertEqual(cfg.get("ui_theme_variant"), "editorial_dark_v1")
            self.assertEqual(cfg.get("ui_density"), "comfortable")
            self.assertEqual(cfg.get("ui_show_tips"), True)
            self.assertEqual(cfg.get("danbooru_pool_connections"), DEFAULT_CONFIG["danbooru_pool_connections"])
            self.assertEqual(cfg.get("thumbnail_batch_size"), DEFAULT_CONFIG["thumbnail_batch_size"])
            self.assertEqual(cfg.get("image_cache_max_mb"), DEFAULT_CONFIG["image_cache_max_mb"])

    def test_invalid_json_uses_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = f"{tmp}/custommaker_config.json"
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("{invalid-json")

            with patch("src.core.app_config.CONFIG_FILE", config_path):
                cfg = AppConfig()

            self.assertEqual(cfg.get("config_version"), CURRENT_CONFIG_VERSION)
            self.assertEqual(cfg.get("ai_mode"), "safe")
            self.assertEqual(cfg.get("ui_language"), "pt-BR")
            self.assertEqual(cfg.get("ui_theme_variant"), "editorial_dark_v1")
            self.assertEqual(cfg.get("ui_density"), "comfortable")
            self.assertEqual(cfg.get("ui_show_tips"), True)
            self.assertEqual(cfg.get("danbooru_retry_total"), DEFAULT_CONFIG["danbooru_retry_total"])
            self.assertEqual(cfg.get("thumbnail_disk_cache_mb"), DEFAULT_CONFIG["thumbnail_disk_cache_mb"])

    def test_save_persists_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = f"{tmp}/custommaker_config.json"

            with patch("src.core.app_config.CONFIG_FILE", config_path):
                cfg = AppConfig()
                cfg.set("log_level", "ERROR")
                cfg.set("max_workers", 2)
                cfg.set("ui_density", "compact")
                cfg.save()

            with open(config_path, "r", encoding="utf-8") as f:
                saved = json.load(f)

            self.assertEqual(saved["log_level"], "ERROR")
            self.assertEqual(saved["max_workers"], 2)
            self.assertEqual(saved["ui_density"], "compact")
            self.assertEqual(saved["config_version"], CURRENT_CONFIG_VERSION)

    def test_invalid_performance_types_fallback_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = f"{tmp}/custommaker_config.json"
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "danbooru_pool_connections": "abc",
                        "danbooru_pool_maxsize": "xyz",
                        "danbooru_retry_total": "oops",
                        "danbooru_retry_backoff": "bad",
                        "danbooru_timeout_search_s": "nope",
                        "danbooru_timeout_tags_s": None,
                        "danbooru_timeout_download_s": "error",
                        "thumbnail_batch_size": "zero",
                        "thumbnail_batch_interval_ms": "nan",
                        "thumbnail_memory_cache_mb": "xx",
                        "thumbnail_disk_cache_mb": "yy",
                        "image_cache_max_mb": "zz",
                    },
                    f,
                )

            with patch("src.core.app_config.CONFIG_FILE", config_path):
                cfg = AppConfig()

            self.assertEqual(cfg.get("danbooru_pool_connections"), DEFAULT_CONFIG["danbooru_pool_connections"])
            self.assertEqual(cfg.get("danbooru_pool_maxsize"), DEFAULT_CONFIG["danbooru_pool_maxsize"])
            self.assertEqual(cfg.get("danbooru_retry_total"), DEFAULT_CONFIG["danbooru_retry_total"])
            self.assertEqual(cfg.get("danbooru_retry_backoff"), DEFAULT_CONFIG["danbooru_retry_backoff"])
            self.assertEqual(cfg.get("danbooru_timeout_search_s"), DEFAULT_CONFIG["danbooru_timeout_search_s"])
            self.assertEqual(cfg.get("danbooru_timeout_tags_s"), DEFAULT_CONFIG["danbooru_timeout_tags_s"])
            self.assertEqual(cfg.get("danbooru_timeout_download_s"), DEFAULT_CONFIG["danbooru_timeout_download_s"])
            self.assertEqual(cfg.get("thumbnail_batch_size"), DEFAULT_CONFIG["thumbnail_batch_size"])
            self.assertEqual(cfg.get("thumbnail_batch_interval_ms"), DEFAULT_CONFIG["thumbnail_batch_interval_ms"])
            self.assertEqual(cfg.get("thumbnail_memory_cache_mb"), DEFAULT_CONFIG["thumbnail_memory_cache_mb"])
            self.assertEqual(cfg.get("thumbnail_disk_cache_mb"), DEFAULT_CONFIG["thumbnail_disk_cache_mb"])
            self.assertEqual(cfg.get("image_cache_max_mb"), DEFAULT_CONFIG["image_cache_max_mb"])
