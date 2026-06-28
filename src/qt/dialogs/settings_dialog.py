"""Dialog de configurações do CustomMaker."""
from src.qt.compat import QT_AVAILABLE, qt_unavailable_error

if QT_AVAILABLE:
    from src.qt.compat import (
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QScrollArea,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
        Qt,
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
                "Timeout busca (s):", self.app_config.get("danbooru_timeout_search_s", 10), 1, 120
            )
            self._timeout_download = self._spin_field(
                "Timeout download (s):", self.app_config.get("danbooru_timeout_download_s", 15), 1, 300
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

            self._max_workers = self._spin_field(
                "Workers paralelos:", self.app_config.get("max_workers") or 4, 1, 16
            )
            self._thumb_mem_mb = self._spin_field(
                "Cache thumb memória (MB):", self.app_config.get("thumbnail_memory_cache_mb", 64), 8, 2048
            )
            self._thumb_disk_mb = self._spin_field(
                "Cache thumb disco (MB):", self.app_config.get("thumbnail_disk_cache_mb", 512), 64, 4096
            )
            self._img_cache_mb = self._spin_field(
                "Cache preview (MB):", self.app_config.get("image_cache_max_mb", 256), 32, 2048
            )

            layout.addRow("Workers paralelos:", self._max_workers)
            layout.addRow("Cache thumb memória (MB):", self._thumb_mem_mb)
            layout.addRow("Cache thumb disco (MB):", self._thumb_disk_mb)
            layout.addRow("Cache preview (MB):", self._img_cache_mb)
            return widget

        # ── Helpers ────────────────────────────────────────────────────────

        @staticmethod
        def _spin_field(label, value, minimum, maximum):
            from src.qt.compat import QLineEdit
            field = QLineEdit()
            field.setText(str(value))
            return field

        def _int_val(self, field, default, minimum, maximum):
            try:
                v = int(field.text())
                return max(minimum, min(maximum, v))
            except (ValueError, TypeError):
                return default

        def _save(self):
            self.app_config.set("ai_mode", self._ai_mode.currentText())
            prompt = self._ai_base_prompt.toPlainText().strip()
            if prompt:
                self.app_config.set("ai_base_prompt", prompt)

            self.app_config.set("danbooru_tag_blacklist", self._blacklist.text().strip())
            self.app_config.set("danbooru_timeout_search_s", self._int_val(self._timeout_search, 10, 1, 120))
            self.app_config.set("danbooru_timeout_download_s", self._int_val(self._timeout_download, 15, 1, 300))

            self.app_config.set("max_workers", self._int_val(self._max_workers, 4, 1, 16))
            self.app_config.set("thumbnail_memory_cache_mb", self._int_val(self._thumb_mem_mb, 64, 8, 2048))
            self.app_config.set("thumbnail_disk_cache_mb", self._int_val(self._thumb_disk_mb, 512, 64, 4096))
            self.app_config.set("image_cache_max_mb", self._int_val(self._img_cache_mb, 256, 32, 2048))

            self.app_config.save()
            self.accept()

else:
    class SettingsDialog:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
