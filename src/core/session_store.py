"""Sessão de trabalho salva em disco: lista de imagens, enquadramentos e bordas.

Sem isto, fechar ou travar o app perdia todo o enquadramento feito. Os
enquadramentos são guardados relativos à borda, porque a posição absoluta da
borda depende do tamanho da janela, que pode ser outro ao restaurar.
"""
import hashlib
import json
import logging
import os

from src.utils.resource_loader import app_data_path


logger = logging.getLogger(__name__)

SESSION_VERSION = 1


def _edit_file_name(path):
    return hashlib.sha1(path.encode("utf-8")).hexdigest() + ".png"


def snapshot_session(editor_state, edited_paths):
    """Dicionário serializável com o estado de trabalho atual."""
    bx, by = editor_state.borda_pos
    states = {}
    for path, state in editor_state.image_states.items():
        if path in editor_state.image_list:
            (x, y), (w, h) = state["pos"], state["size"]
            states[path] = {"rel_pos": [int(x - bx), int(y - by)], "size": [int(w), int(h)]}
    return {
        "version": SESSION_VERSION,
        "images": list(editor_state.image_list),
        "current_index": editor_state.current_image_index,
        "states": states,
        "auto_framed": sorted(p for p in editor_state.auto_framed if p in states),
        "dirty": sorted(p for p in editor_state.image_dirty if p in editor_state.image_list),
        "individual_bordas": dict(editor_state.individual_bordas),
        "custom_borda_hex_individual": dict(editor_state.custom_borda_hex_individual),
        "selected_borda": editor_state.selected_borda,
        "custom_borda_hex": editor_state.custom_borda_hex,
        "animation_type": editor_state.animation_type,
        "border_style": editor_state.border_style,
        "adjustments": {p: dict(a) for p, a in editor_state.image_adjustments.items() if p in editor_state.image_list},
        "edits": {path: _edit_file_name(path) for path in edited_paths if path in editor_state.image_list},
    }


def apply_session(data, editor_state):
    """Aplica `data` num EditorState vazio. Devolve os paths que não existem mais."""
    bx, by = editor_state.borda_pos
    images = [p for p in data.get("images", []) if isinstance(p, str)]
    present = [p for p in images if os.path.isfile(p)]
    missing = [p for p in images if p not in present]
    editor_state.image_list = present
    for path, state in (data.get("states") or {}).items():
        if path not in present:
            continue
        try:
            (rx, ry), (w, h) = state["rel_pos"], state["size"]
            editor_state.image_states[path] = {"pos": (bx + int(rx), by + int(ry)), "size": (int(w), int(h))}
        except (KeyError, TypeError, ValueError):
            continue
    editor_state.auto_framed = {p for p in data.get("auto_framed", []) if p in editor_state.image_states}
    editor_state.image_dirty = {p for p in data.get("dirty", []) if p in present}
    editor_state.individual_bordas = {
        p: b for p, b in (data.get("individual_bordas") or {}).items() if p in present
    }
    editor_state.custom_borda_hex_individual = {
        p: c for p, c in (data.get("custom_borda_hex_individual") or {}).items() if p in present
    }
    for field in ("selected_borda", "custom_borda_hex", "animation_type"):
        value = data.get(field)
        if isinstance(value, str) and value:
            setattr(editor_state, field, value)
    # sessões salvas antes dos estilos não têm a chave: abrem com o simples
    from src.core.border_styles import normalize_style
    editor_state.border_style = normalize_style(data.get("border_style"))
    from src.core.color_adjustments import normalize
    adjustments = data.get("adjustments") if isinstance(data.get("adjustments"), dict) else {}
    editor_state.image_adjustments = {
        p: value for p, value in ((p, normalize(a)) for p, a in adjustments.items() if p in present) if value
    }
    index = data.get("current_index")
    if isinstance(index, int) and 0 <= index < len(present):
        editor_state.current_image_index = index
    elif present:
        editor_state.current_image_index = 0
    return missing


class SessionStore:
    """Grava/lê a sessão em `session.json` e as imagens editadas em `session_edits/`."""

    def __init__(self, session_file=None, edits_dir=None):
        self.session_file = session_file or app_data_path("session.json")
        self.edits_dir = edits_dir or app_data_path("session_edits")

    def load(self):
        if not os.path.exists(self.session_file):
            return None
        try:
            with open(self.session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as exc:
            logger.warning("Sessão salva ilegível, ignorando: %s", exc)
            return None
        if not isinstance(data, dict) or data.get("version") != SESSION_VERSION or not data.get("images"):
            return None
        return data

    def save(self, data):
        """Escrita atômica (tmp + replace): um crash no meio não corrompe a sessão."""
        tmp_path = f"{self.session_file}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp_path, self.session_file)
        except OSError as exc:
            logger.warning("Não foi possível salvar a sessão: %s", exc)
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            return False
        self._prune_edits(set((data.get("edits") or {}).values()))
        return True

    def clear(self):
        for path in (self.session_file, f"{self.session_file}.tmp"):
            try:
                os.remove(path)
            except OSError:
                pass
        self._prune_edits(set())

    def edit_path(self, image_path):
        return os.path.join(self.edits_dir, _edit_file_name(image_path))

    def write_edit(self, image_path, image):
        """Grava a imagem editada (rotação/IA) de `image_path` como PNG."""
        os.makedirs(self.edits_dir, exist_ok=True)
        target = self.edit_path(image_path)
        tmp_path = target + ".tmp"
        image.save(tmp_path, format="PNG")
        os.replace(tmp_path, target)

    def _prune_edits(self, keep):
        try:
            names = os.listdir(self.edits_dir)
        except OSError:
            return
        for name in names:
            # .tmp = gravação em andamento num worker; não é lixo ainda
            if name not in keep and not name.endswith(".tmp"):
                try:
                    os.remove(os.path.join(self.edits_dir, name))
                except OSError:
                    pass
