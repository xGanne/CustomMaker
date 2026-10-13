"""Dialog de configurações do CustomMaker."""
from src.config.settings import DEFAULT_THEME_VARIANT, THEME_LABELS
from src.qt.compat import QT_AVAILABLE, qt_unavailable_error
from src.qt.theme import tokens

if QT_AVAILABLE:
    from src.qt.compat import (
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QSpinBox,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )


if QT_AVAILABLE:
    class SettingsDialog(QDialog):
        def __init__(self, app_config, parent=None):
            super().__init__(parent)
            self.app_config = app_config
            self.theme_changed = False
            self.setWindowTitle("Configurações")
            self.resize(540, 480)
            self.setModal(True)

            layout = QVBoxLayout(self)
            tabs = QTabWidget()
            layout.addWidget(tabs, 1)

            tabs.addTab(self._build_appearance_tab(), "Aparência")
            tabs.addTab(self._build_ai_tab(), "IA")
            tabs.addTab(self._build_danbooru_tab(), "Danbooru")
            tabs.addTab(self._build_performance_tab(), "Performance")

            buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
            buttons.accepted.connect(self._save)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)

        # ── Aba Aparência (M7) ────────────────────────────────────────────

        def _build_appearance_tab(self):
            widget = QWidget()
            layout = QVBoxLayout(widget)
            form = QFormLayout()
            self._theme = QComboBox()
            for variant, label in THEME_LABELS.items():
                self._theme.addItem(label, variant)
            current = self.app_config.get("ui_theme_variant", DEFAULT_THEME_VARIANT)
            index = self._theme.findData(current)
            self._theme.setCurrentIndex(index if index >= 0 else 0)
            form.addRow("Tema:", self._theme)
            layout.addLayout(form)

            theme_note = QLabel("A troca de tema é aplicada ao reiniciar o programa.")
            theme_note.setWordWrap(True)
            theme_note.setStyleSheet(f"color: {tokens()['text_muted']}; font-size: 11px; margin-top: 8px;")
            layout.addWidget(theme_note)
            layout.addStretch(1)
            return widget

        # ── Aba IA ────────────────────────────────────────────────────────

        def _build_ai_tab(self):
            widget = QWidget()
            layout = QVBoxLayout(widget)
            form = QFormLayout()

            self._ai_mode = QComboBox()
            self._ai_mode.addItems(["safe", "off", "provider_default"])
            self._ai_mode.setCurrentText(self.app_config.get("ai_mode", "safe"))
            form.addRow("Modo da IA:", self._ai_mode)

            layout.addLayout(form)

            prompt_label = QLabel("Instrução base enviada ao Gemini antes do prompt do usuário:")
            prompt_label.setWordWrap(True)
            prompt_label.setStyleSheet(f"color: {tokens()['text_muted']}; font-size: 11px; margin-top: 8px;")
            self._ai_base_prompt = QTextEdit()
            self._ai_base_prompt.setMinimumHeight(120)
            self._ai_base_prompt.setPlainText(self.app_config.get("ai_base_prompt", ""))
            layout.addWidget(prompt_label)
            layout.addWidget(self._ai_base_prompt)
            layout.addStretch(1)
            return widget

        # ── Aba Danbooru ──────────────────────────────────────────────────

        def _build_danbooru_tab(self):
            widget = QWidget()
            layout = QVBoxLayout(widget)
            form = QFormLayout()

            blacklist_hint = QLabel("Tags excluídas de buscas (separadas por espaço):")
            blacklist_hint.setWordWrap(True)
            blacklist_hint.setStyleSheet(f"color: {tokens()['text_muted']}; font-size: 11px;")
            layout.addWidget(blacklist_hint)
            self._blacklist = QLineEdit()
            self._blacklist.setText(self.app_config.get("danbooru_tag_blacklist", ""))
            self._blacklist.setPlaceholderText("ex: gore violence nsfw")
            layout.addWidget(self._blacklist)

            layout.addSpacing(8)

            self._timeout_search = self._spin_field(
                self.app_config.get("danbooru_timeout_search_s", 10), 1, 120
            )
            self._timeout_download = self._spin_field(
                self.app_config.get("danbooru_timeout_download_s", 15), 1, 300
            )
            self._page_size = self._spin_field(self.app_config.get("danbooru_page_size", 40), 10, 200)
            self._page_size.setSingleStep(10)
            self._page_size.setToolTip(
                "Mais resultados por página = menos troca de página e mais candidatos "
                "para o Auto-selecionar. Vale a partir da próxima busca."
            )
            for label, widget_ref in [
                ("Resultados por página:", self._page_size),
                ("Timeout busca (s):", self._timeout_search),
                ("Timeout download (s):", self._timeout_download),
            ]:
                form.addRow(label, widget_ref)
            layout.addLayout(form)

            layout.addSpacing(10)
            account_hint = QLabel(
                "Conta (opcional): sem login o Danbooru aceita só 2 tags por busca; Gold "
                "aceita 6 e Platinum 12. A chave de API fica em danbooru.donmai.us › "
                "My Account › API Key e é salva só no arquivo .env, nunca no config."
            )
            account_hint.setWordWrap(True)
            account_hint.setStyleSheet(f"color: {tokens()['text_muted']}; font-size: 11px;")
            layout.addWidget(account_hint)
            from src.core.danbooru import DANBOORU_API_KEY_KEY, DANBOORU_LOGIN_KEY
            from src.core.env_file import read_env_values
            env = read_env_values()
            account_form = QFormLayout()
            self._danbooru_login = QLineEdit(env.get(DANBOORU_LOGIN_KEY, ""))
            self._danbooru_login.setPlaceholderText("seu nome de usuário")
            self._danbooru_api_key = QLineEdit(env.get(DANBOORU_API_KEY_KEY, ""))
            self._danbooru_api_key.setEchoMode(QLineEdit.Password)
            self._danbooru_api_key.setPlaceholderText("chave de API")
            account_form.addRow("Login:", self._danbooru_login)
            account_form.addRow("Chave de API:", self._danbooru_api_key)
            layout.addLayout(account_form)
            test_row = QHBoxLayout()
            self._test_account_button = QPushButton("Testar conexão")
            self._test_account_button.setProperty("class", "secondary")
            self._test_account_button.clicked.connect(self._test_danbooru_account)
            self._account_status = QLabel("")
            self._account_status.setWordWrap(True)
            test_row.addWidget(self._test_account_button)
            test_row.addWidget(self._account_status, 1)
            layout.addLayout(test_row)
            layout.addStretch(1)
            return widget

        def _test_danbooru_account(self):
            from src.core.danbooru import DanbooruClient
            from src.qt.compat import QApplication, Qt
            login = self._danbooru_login.text().strip()
            api_key = self._danbooru_api_key.text().strip()
            auth = (login, api_key) if login and api_key else None
            client = DanbooruClient(config=self.app_config)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                profile = client.fetch_profile(auth=auth)
                if auth is None:
                    text = f"Sem conta: limite de {profile['tag_query_limit']} tags por busca."
                else:
                    text = (
                        f"Conectado como {profile['name']} ({profile['level']}): "
                        f"limite de {profile['tag_query_limit']} tags por busca."
                    )
            except Exception as exc:
                text = str(exc)
            finally:
                QApplication.restoreOverrideCursor()
                client.close()
            self._account_status.setText(text)

        # ── Aba Performance ───────────────────────────────────────────────

        def _build_performance_tab(self):
            widget = QWidget()
            layout = QFormLayout(widget)

            # F12: 0 = automático (persistido como None); evita perder o modo
            # auto ao abrir e salvar o diálogo
            self._max_workers = self._spin_field(self.app_config.get("max_workers") or 0, 0, 16)
            self._max_workers.setSpecialValueText("Automático")
            self._thumb_mem_mb = self._spin_field(
                self.app_config.get("thumbnail_memory_cache_mb", 64), 8, 2048
            )
            self._thumb_disk_mb = self._spin_field(
                self.app_config.get("thumbnail_disk_cache_mb", 512), 64, 4096
            )
            self._img_cache_mb = self._spin_field(
                self.app_config.get("image_cache_max_mb", 256), 32, 2048
            )

            layout.addRow("Workers paralelos:", self._max_workers)
            layout.addRow("Cache thumb memória (MB):", self._thumb_mem_mb)
            layout.addRow("Cache thumb disco (MB):", self._thumb_disk_mb)
            layout.addRow("Cache preview (MB):", self._img_cache_mb)

            restart_note = QLabel("Alterações de performance têm efeito após reiniciar o programa.")
            restart_note.setWordWrap(True)
            restart_note.setStyleSheet(f"color: {tokens()['text_muted']}; font-size: 11px; margin-top: 8px;")
            layout.addRow(restart_note)
            return widget

        # ── Helpers ────────────────────────────────────────────────────────

        @staticmethod
        def _spin_field(value, minimum, maximum):
            field = QSpinBox()
            field.setRange(minimum, maximum)
            try:
                field.setValue(int(value))
            except (ValueError, TypeError):
                field.setValue(minimum)
            return field

        def _save(self):
            theme = self._theme.currentData()
            self.theme_changed = theme != self.app_config.get("ui_theme_variant", DEFAULT_THEME_VARIANT)
            self.app_config.set("ui_theme_variant", theme)
            self.app_config.set("ai_mode", self._ai_mode.currentText())
            prompt = self._ai_base_prompt.toPlainText().strip()
            if prompt:
                self.app_config.set("ai_base_prompt", prompt)

            self.app_config.set("danbooru_tag_blacklist", self._blacklist.text().strip())
            self.app_config.set("danbooru_timeout_search_s", self._timeout_search.value())
            self.app_config.set("danbooru_timeout_download_s", self._timeout_download.value())
            self.app_config.set("danbooru_page_size", self._page_size.value())
            from src.core.danbooru import DANBOORU_API_KEY_KEY, DANBOORU_LOGIN_KEY
            from src.core.env_file import read_env_values, update_env_values
            account = {
                DANBOORU_LOGIN_KEY: self._danbooru_login.text().strip(),
                DANBOORU_API_KEY_KEY: self._danbooru_api_key.text().strip(),
            }
            current = read_env_values()
            if any((current.get(k) or "") != v for k, v in account.items()):
                try:
                    update_env_values(account)
                except OSError as exc:
                    from src.qt.compat import QMessageBox
                    QMessageBox.warning(self, "Configurações", f"Não foi possível salvar a conta no .env: {exc}")

            workers = self._max_workers.value()
            self.app_config.set("max_workers", workers if workers > 0 else None)
            self.app_config.set("thumbnail_memory_cache_mb", self._thumb_mem_mb.value())
            self.app_config.set("thumbnail_disk_cache_mb", self._thumb_disk_mb.value())
            self.app_config.set("image_cache_max_mb", self._img_cache_mb.value())

            self.app_config.save()
            self.accept()

else:
    class SettingsDialog:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
