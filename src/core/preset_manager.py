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


def apply_preset_to_state(data, editor_state, borda_hex, adjust_paths=()):
    """Aplica um preset ao estado do editor (sem interface) e devolve o resto.

    Borda, cor, animação, estilo de borda e ajustes de cor (nas imagens de
    `adjust_paths`) vão direto para `editor_state`. Enquadramento padrão e
    blacklist do Danbooru dependem de quem chama (a janela reenquadra e grava a
    config; o modo --batch não grava nada), então voltam no dicionário.
    """
    from src.core.border_styles import normalize_style

    if not isinstance(data, dict):
        return {}
    border_name = data.get("border_name", editor_state.selected_borda)
    if border_name in borda_hex or border_name == "Cor Personalizada":
        editor_state.selected_borda = border_name
    custom_color = data.get("border_color")
    if isinstance(custom_color, str) and custom_color.startswith("#") and len(custom_color) == 7:
        editor_state.custom_borda_hex = custom_color
    animation_type = data.get("animation_type")
    if isinstance(animation_type, str):
        editor_state.animation_type = animation_type
    if "border_style" in data:  # presets antigos não têm: mantém o estilo atual
        editor_state.border_style = normalize_style(data.get("border_style"))
    rest = {}
    adjustments = data.get("color_adjustments")
    if isinstance(adjustments, dict):
        for path in adjust_paths:
            editor_state.set_image_adjustments(path, adjustments)
        rest["color_adjustments"] = adjustments
    # M11: partes opcionais — só existem se o preset foi salvo com elas
    if data.get("default_framing") in ("auto_fit", "intelligent"):
        rest["default_framing"] = data["default_framing"]
    if isinstance(data.get("danbooru_blacklist"), str):
        rest["danbooru_blacklist"] = data["danbooru_blacklist"].strip()
    return rest
