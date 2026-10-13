"""
SessionMixin — salvamento automático e restauração da sessão de trabalho.

Responsabilidades:
  • Salvar periodicamente (e ao fechar) a lista, os enquadramentos e as bordas
  • Gravar em segundo plano as imagens com pixels editados (rotação, IA)
  • Oferecer a restauração da sessão anterior ao abrir o app
"""
import json
import logging

from PIL import Image

from src.core.session_store import apply_session, snapshot_session


logger = logging.getLogger(__name__)


class SessionMixin:

    SESSION_AUTOSAVE_MS = 4000

    def _init_session(self, session_store):
        """Liga o salvamento automático. Sem `session_store` (ex.: testes), nada é salvo."""
        self.session_store = session_store
        self._session_signature = None
        self._session_saved_edits = {}  # path -> id() da imagem editada já gravada
        self._session_edit_seq = 0
        if session_store is None:
            return
        from src.qt.compat import QTimer
        self._session_timer = QTimer(self)
        self._session_timer.timeout.connect(self._autosave_session)
        self._session_timer.start(self.SESSION_AUTOSAVE_MS)
        QTimer.singleShot(0, self._offer_session_restore)

    # ── Salvamento ──────────────────────────────────────────────────────────

    def _autosave_session(self, force=False):
        store = getattr(self, "session_store", None)
        if store is None:
            return
        data = snapshot_session(self.editor_state, list(self.edited_images))
        if not data["images"]:
            if self._session_signature is not None or force:
                store.clear()
            self._session_signature = None
            self._session_saved_edits.clear()
            return
        self._save_session_edits(store, force)
        signature = json.dumps(data, sort_keys=True)
        if signature == self._session_signature and not force:
            return
        if store.save(data):
            self._session_signature = signature

    def _save_session_edits(self, store, synchronous):
        """Grava as imagens editadas que mudaram desde o último salvamento."""
        pending = []
        for path, image in self.edited_images.items():
            if self._session_saved_edits.get(path) != id(image):
                self._session_saved_edits[path] = id(image)
                pending.append((path, image.copy()))
        for path in list(self._session_saved_edits):
            if path not in self.edited_images:
                self._session_saved_edits.pop(path, None)
        if not pending:
            return

        def write_all(*_args):
            for path, image in pending:
                try:
                    store.write_edit(path, image)
                except Exception as exc:
                    logger.warning("Não foi possível salvar a edição de %s na sessão: %s", path, exc)
                finally:
                    image.close()

        if synchronous:
            write_all()
            return
        # PNG de uma imagem grande leva ~1s: fora da GUI thread
        self._session_edit_seq += 1
        self.task_runner.submit(f"qt_session_edits_{self._session_edit_seq}", write_all)

    # ── Restauração ─────────────────────────────────────────────────────────

    def _offer_session_restore(self):
        store = self.session_store
        data = store.load() if store is not None else None
        if not data:
            return
        from src.qt.compat import QMessageBox
        count = len(data.get("images") or [])
        adjusted = len(set(data.get("states") or {}) - set(data.get("auto_framed") or []))
        answer = QMessageBox.question(
            self,
            "Restaurar sessão",
            f"Restaurar a sessão anterior?\n\n{count} imagem(ns) na lista, {adjusted} com ajuste manual.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer == QMessageBox.Yes:
            self.restore_session(data)
        else:
            store.clear()

    def restore_session(self, data):
        self._reset_workspace()
        missing = apply_session(data, self.editor_state)
        store = self.session_store
        for path, file_name in (data.get("edits") or {}).items():
            if path not in self.editor_state.image_list or store is None:
                continue
            try:
                with Image.open(store.edit_path(path)) as edited:
                    self.edited_images[path] = edited.convert("RGBA")
                self._session_saved_edits[path] = id(self.edited_images[path])
            except Exception as exc:
                logger.warning("Edição salva de %s não pôde ser lida: %s", path, exc)

        self.image_list_panel.set_paths(self.editor_state.image_list)
        self.refresh_list_indicators()
        self.refresh_options_bar()
        self.editor_tab.refresh_from_state()
        if not self.editor_state.image_list:
            self.show_warning("Restaurar sessão", "Nenhuma das imagens da sessão anterior existe mais.")
            return
        # imagens sem enquadramento salvo recebem o padrão em segundo plano
        self._precompute_default_framing(
            [p for p in self.editor_state.image_list if p not in self.editor_state.image_states]
        )
        self.load_image(self.editor_state.current_image_index or 0)
        self._session_signature = None  # regrava na próxima rodada
        if missing:
            names = ", ".join(path.replace("\\", "/").rsplit("/", 1)[-1] for path in missing[:5])
            more = "..." if len(missing) > 5 else ""
            self.show_warning(
                "Restaurar sessão",
                f"{len(missing)} imagem(ns) não existem mais e foram puladas: {names}{more}",
            )
        else:
            self.show_status(f"Sessão restaurada: {len(self.editor_state.image_list)} imagem(ns).")
