import json
import logging
import os
from copy import deepcopy

from src.config.settings import (
    CONFIG_FILE,
    DANBOORU_POOL_CONNECTIONS_DEFAULT,
    DANBOORU_POOL_MAXSIZE_DEFAULT,
    DANBOORU_RETRY_BACKOFF_DEFAULT,
    DANBOORU_RETRY_TOTAL_DEFAULT,
    DANBOORU_TIMEOUT_DOWNLOAD_S_DEFAULT,
    DANBOORU_TIMEOUT_SEARCH_S_DEFAULT,
    DANBOORU_TIMEOUT_TAGS_S_DEFAULT,
    IMAGE_CACHE_MAX_MB_DEFAULT,
    THUMBNAIL_BATCH_INTERVAL_MS_DEFAULT,
    THUMBNAIL_BATCH_SIZE_DEFAULT,
    THUMBNAIL_DISK_CACHE_MB_DEFAULT,
    THUMBNAIL_MEMORY_CACHE_MB_DEFAULT,
)


logger = logging.getLogger(__name__)


CURRENT_CONFIG_VERSION = 4


DEFAULT_CONFIG = {
    "config_version": CURRENT_CONFIG_VERSION,
    "last_folder": None,
    "last_global_borda": "White",
    "appearance_mode": "Dark",
    "color_theme": "blue",
    "ui_theme_variant": "editorial_dark_v1",
    "ui_density": "comfortable",
    "ui_show_tips": True,
    "log_level": "INFO",
    "max_workers": None,
    "ai_mode": "safe",
    "ai_base_prompt": (
        "Analyze the image and describe the requested visual edit while preserving the original pose, "
        "composition, character identity, and art style. Return only the visual description."
    ),
    "ui_language": "pt-BR",
    "feature_flags": {},
    "danbooru_pool_connections": DANBOORU_POOL_CONNECTIONS_DEFAULT,
    "danbooru_pool_maxsize": DANBOORU_POOL_MAXSIZE_DEFAULT,
    "danbooru_retry_total": DANBOORU_RETRY_TOTAL_DEFAULT,
    "danbooru_retry_backoff": DANBOORU_RETRY_BACKOFF_DEFAULT,
    "danbooru_timeout_search_s": DANBOORU_TIMEOUT_SEARCH_S_DEFAULT,
    "danbooru_timeout_tags_s": DANBOORU_TIMEOUT_TAGS_S_DEFAULT,
    "danbooru_timeout_download_s": DANBOORU_TIMEOUT_DOWNLOAD_S_DEFAULT,
    "thumbnail_batch_size": THUMBNAIL_BATCH_SIZE_DEFAULT,
    "thumbnail_batch_interval_ms": THUMBNAIL_BATCH_INTERVAL_MS_DEFAULT,
    "thumbnail_memory_cache_mb": THUMBNAIL_MEMORY_CACHE_MB_DEFAULT,
    "thumbnail_disk_cache_mb": THUMBNAIL_DISK_CACHE_MB_DEFAULT,
    "image_cache_max_mb": IMAGE_CACHE_MAX_MB_DEFAULT,
}


def _coerce_int(value, default, minimum=None, maximum=None):
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return default

    if minimum is not None:
        coerced = max(minimum, coerced)
    if maximum is not None:
        coerced = min(maximum, coerced)
    return coerced


def _coerce_float(value, default, minimum=None, maximum=None):
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        return default

    if minimum is not None:
        coerced = max(minimum, coerced)
    if maximum is not None:
        coerced = min(maximum, coerced)
    return coerced


class AppConfig:
    def __init__(self):
        self.config_data = deepcopy(DEFAULT_CONFIG)
        self.load()

    def _migrate(self, loaded: dict) -> dict:
        migrated = deepcopy(DEFAULT_CONFIG)
        if isinstance(loaded, dict):
            migrated.update(loaded)

        version = migrated.get("config_version")
        if not isinstance(version, int):
            version = 1

        if version < CURRENT_CONFIG_VERSION:
            migrated["config_version"] = CURRENT_CONFIG_VERSION

        if not isinstance(migrated.get("feature_flags"), dict):
            migrated["feature_flags"] = {}

        if not isinstance(migrated.get("log_level"), str):
            migrated["log_level"] = DEFAULT_CONFIG["log_level"]

        if migrated.get("ui_theme_variant") not in {"editorial_dark_v1"}:
            migrated["ui_theme_variant"] = DEFAULT_CONFIG["ui_theme_variant"]

        if migrated.get("ui_density") not in {"comfortable", "compact"}:
            migrated["ui_density"] = DEFAULT_CONFIG["ui_density"]

        if not isinstance(migrated.get("ui_show_tips"), bool):
            migrated["ui_show_tips"] = DEFAULT_CONFIG["ui_show_tips"]

        max_workers = migrated.get("max_workers")
        if max_workers is not None:
            try:
                max_workers = int(max_workers)
                migrated["max_workers"] = max(1, max_workers)
            except (TypeError, ValueError):
                migrated["max_workers"] = DEFAULT_CONFIG["max_workers"]

        if migrated.get("ai_mode") not in {"safe", "off", "provider_default"}:
            migrated["ai_mode"] = DEFAULT_CONFIG["ai_mode"]

        if not isinstance(migrated.get("ai_base_prompt"), str) or not migrated.get("ai_base_prompt").strip():
            migrated["ai_base_prompt"] = DEFAULT_CONFIG["ai_base_prompt"]

        if not isinstance(migrated.get("ui_language"), str):
            migrated["ui_language"] = DEFAULT_CONFIG["ui_language"]

        migrated["danbooru_pool_connections"] = _coerce_int(
            migrated.get("danbooru_pool_connections"),
            DEFAULT_CONFIG["danbooru_pool_connections"],
            minimum=1,
            maximum=256,
        )
        migrated["danbooru_pool_maxsize"] = _coerce_int(
            migrated.get("danbooru_pool_maxsize"),
            DEFAULT_CONFIG["danbooru_pool_maxsize"],
            minimum=1,
            maximum=256,
        )
        migrated["danbooru_retry_total"] = _coerce_int(
            migrated.get("danbooru_retry_total"),
            DEFAULT_CONFIG["danbooru_retry_total"],
            minimum=0,
            maximum=10,
        )
        migrated["danbooru_retry_backoff"] = _coerce_float(
            migrated.get("danbooru_retry_backoff"),
            DEFAULT_CONFIG["danbooru_retry_backoff"],
            minimum=0.0,
            maximum=10.0,
        )
        migrated["danbooru_timeout_search_s"] = _coerce_int(
            migrated.get("danbooru_timeout_search_s"),
            DEFAULT_CONFIG["danbooru_timeout_search_s"],
            minimum=1,
            maximum=120,
        )
        migrated["danbooru_timeout_tags_s"] = _coerce_int(
            migrated.get("danbooru_timeout_tags_s"),
            DEFAULT_CONFIG["danbooru_timeout_tags_s"],
            minimum=1,
            maximum=120,
        )
        migrated["danbooru_timeout_download_s"] = _coerce_int(
            migrated.get("danbooru_timeout_download_s"),
            DEFAULT_CONFIG["danbooru_timeout_download_s"],
            minimum=1,
            maximum=300,
        )
        migrated["thumbnail_batch_size"] = _coerce_int(
            migrated.get("thumbnail_batch_size"),
            DEFAULT_CONFIG["thumbnail_batch_size"],
            minimum=1,
            maximum=32,
        )
        migrated["thumbnail_batch_interval_ms"] = _coerce_int(
            migrated.get("thumbnail_batch_interval_ms"),
            DEFAULT_CONFIG["thumbnail_batch_interval_ms"],
            minimum=1,
            maximum=1000,
        )
        migrated["thumbnail_memory_cache_mb"] = _coerce_int(
            migrated.get("thumbnail_memory_cache_mb"),
            DEFAULT_CONFIG["thumbnail_memory_cache_mb"],
            minimum=8,
            maximum=2048,
        )
        migrated["thumbnail_disk_cache_mb"] = _coerce_int(
            migrated.get("thumbnail_disk_cache_mb"),
            DEFAULT_CONFIG["thumbnail_disk_cache_mb"],
            minimum=16,
            maximum=8192,
        )
        migrated["image_cache_max_mb"] = _coerce_int(
            migrated.get("image_cache_max_mb"),
            DEFAULT_CONFIG["image_cache_max_mb"],
            minimum=32,
            maximum=8192,
        )

        return migrated

    def load(self):
        if not os.path.exists(CONFIG_FILE):
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.config_data = self._migrate(loaded)
        except json.JSONDecodeError:
            logger.warning("Erro ao ler %s (JSON inválido). Usando padrão.", CONFIG_FILE)
            self.config_data = deepcopy(DEFAULT_CONFIG)
        except OSError as exc:
            logger.error("Falha ao abrir %s: %s", CONFIG_FILE, exc)
            self.config_data = deepcopy(DEFAULT_CONFIG)

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False)
        except OSError as exc:
            logger.error("Não foi possível salvar config em %s: %s", CONFIG_FILE, exc)

    def get(self, key, default=None):
        return self.config_data.get(key, default)

    def set(self, key, value):
        self.config_data[key] = value
