from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.core.app_config import DEFAULT_CONFIG


ImagePlacement = Dict[str, Tuple[int, int]]


@dataclass
class EditorState:
    image_list: List[str] = field(default_factory=list)
    current_image_index: Optional[int] = None
    image_states: Dict[str, ImagePlacement] = field(default_factory=dict)
    individual_bordas: Dict[str, str] = field(default_factory=dict)
    custom_borda_hex: str = "#FFFFFF"
    custom_borda_hex_individual: Dict[str, str] = field(default_factory=dict)
    selected_borda: str = "White"
    animation_type: str = "Nenhuma"
    uploaded_links: List[str] = field(default_factory=list)
    borda_pos: Tuple[int, int] = (0, 0)

    @property
    def current_image_path(self) -> Optional[str]:
        if self.current_image_index is None:
            return None
        if self.current_image_index < 0 or self.current_image_index >= len(self.image_list):
            return None
        return self.image_list[self.current_image_index]

    @property
    def has_animation(self) -> bool:
        return self.animation_type != "Nenhuma"

    def resolve_border_name(self, path: Optional[str] = None) -> str:
        if path:
            return self.individual_bordas.get(path, self.selected_borda)
        return self.selected_borda

    def resolve_border_hex(self, borda_hex: Dict[str, str], path: Optional[str] = None) -> str:
        border_name = self.resolve_border_name(path)
        if border_name == "Cor Personalizada":
            if path:
                return self.custom_borda_hex_individual.get(path, self.custom_borda_hex)
            return self.custom_borda_hex
        return borda_hex.get(border_name, "#FFFFFF")

    def set_image_state(self, path: str, pos: Tuple[int, int], size: Tuple[int, int]) -> None:
        self.image_states[path] = {"pos": pos, "size": size}

    def remove_image(self, path: str) -> None:
        self.image_states.pop(path, None)
        self.individual_bordas.pop(path, None)
        self.custom_borda_hex_individual.pop(path, None)
        self.uploaded_links = [link for link in self.uploaded_links if path not in link]
        if path in self.image_list:
            index = self.image_list.index(path)
            self.image_list.pop(index)
            if not self.image_list:
                self.current_image_index = None
            elif self.current_image_index is not None:
                if index < self.current_image_index:
                    self.current_image_index -= 1
                elif index == self.current_image_index:
                    self.current_image_index = min(index, len(self.image_list) - 1)

    def reset_images(self) -> None:
        self.image_list.clear()
        self.current_image_index = None
        self.image_states.clear()
        self.individual_bordas.clear()
        self.custom_borda_hex_individual.clear()
        self.uploaded_links.clear()


@dataclass
class UiPreferences:
    appearance_mode: str = DEFAULT_CONFIG["appearance_mode"]
    last_folder: Optional[str] = DEFAULT_CONFIG["last_folder"]
    last_global_borda: str = DEFAULT_CONFIG["last_global_borda"]
    max_workers: Optional[int] = DEFAULT_CONFIG["max_workers"]
    image_cache_max_mb: int = DEFAULT_CONFIG["image_cache_max_mb"]
    thumbnail_batch_size: int = DEFAULT_CONFIG["thumbnail_batch_size"]
    thumbnail_batch_interval_ms: int = DEFAULT_CONFIG["thumbnail_batch_interval_ms"]
    thumbnail_memory_cache_mb: int = DEFAULT_CONFIG["thumbnail_memory_cache_mb"]
    thumbnail_disk_cache_mb: int = DEFAULT_CONFIG["thumbnail_disk_cache_mb"]

    @classmethod
    def from_app_config(cls, app_config):
        return cls(
            appearance_mode=app_config.get("appearance_mode", DEFAULT_CONFIG["appearance_mode"]),
            last_folder=app_config.get("last_folder", DEFAULT_CONFIG["last_folder"]),
            last_global_borda=app_config.get("last_global_borda", DEFAULT_CONFIG["last_global_borda"]),
            max_workers=app_config.get("max_workers", DEFAULT_CONFIG["max_workers"]),
            image_cache_max_mb=app_config.get("image_cache_max_mb", DEFAULT_CONFIG["image_cache_max_mb"]),
            thumbnail_batch_size=app_config.get("thumbnail_batch_size", DEFAULT_CONFIG["thumbnail_batch_size"]),
            thumbnail_batch_interval_ms=app_config.get(
                "thumbnail_batch_interval_ms",
                DEFAULT_CONFIG["thumbnail_batch_interval_ms"],
            ),
            thumbnail_memory_cache_mb=app_config.get(
                "thumbnail_memory_cache_mb",
                DEFAULT_CONFIG["thumbnail_memory_cache_mb"],
            ),
            thumbnail_disk_cache_mb=app_config.get(
                "thumbnail_disk_cache_mb",
                DEFAULT_CONFIG["thumbnail_disk_cache_mb"],
            ),
        )

    def save_to_app_config(self, app_config) -> None:
        app_config.set("appearance_mode", self.appearance_mode)
        app_config.set("last_folder", self.last_folder)
        app_config.set("last_global_borda", self.last_global_borda)
        app_config.set("max_workers", self.max_workers)
        app_config.set("image_cache_max_mb", self.image_cache_max_mb)
        app_config.set("thumbnail_batch_size", self.thumbnail_batch_size)
        app_config.set("thumbnail_batch_interval_ms", self.thumbnail_batch_interval_ms)
        app_config.set("thumbnail_memory_cache_mb", self.thumbnail_memory_cache_mb)
        app_config.set("thumbnail_disk_cache_mb", self.thumbnail_disk_cache_mb)
