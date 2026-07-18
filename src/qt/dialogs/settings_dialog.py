"""Dialog de configurações do CustomMaker."""
from src.qt.compat import QT_AVAILABLE, qt_unavailable_error

if QT_AVAILABLE:
    from src.qt.compat import (
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QLabel,
        QLineEdit,
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
            self.setWindowTitle("Configurações")
            self.resize(540, 480)
            self.setModal(True)

            layout = QVBoxLayout(self)
            tabs = QTabWidget()
            layout.addWidget(tabs, 1)

            tabs.addTab(self._build_ai_tab(), "IA")
            tabs.addTab(self._build_danbooru_tab(), "Danbooru")
            tabs.addTab(self._build_performance_tab(), "Performance")

            buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
            buttons.accepted.connect(self._save)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)

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
            prompt_label.setStyleSheet("color: #7B879D; font-size: 11px; margin-top: 8px;")
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
            blacklist_hint.setStyleSheet("color: #7B879D; font-size: 11px;")
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
            for label, widget_ref in [
                ("Timeout busca (s):", self._timeout_search),
                ("Timeout download (s):", self._timeout_download),
            ]:
                form.addRow(label, widget_ref)
            layout.addLayout(form)
            layout.addStretch(1)
            return widget

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
            restart_note.setStyleSheet("color: #7B879D; font-size: 11px; margin-top: 8px;")
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
            self.app_config.set("ai_mode", self._ai_mode.currentText())
            prompt = self._ai_base_prompt.toPlainText().strip()
            if prompt:
                self.app_config.set("ai_base_prompt", prompt)

            self.app_config.set("danbooru_tag_blacklist", self._blacklist.text().strip())
            self.app_config.set("danbooru_timeout_search_s", self._timeout_search.value())
            self.app_config.set("danbooru_timeout_download_s", self._timeout_download.value())

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
