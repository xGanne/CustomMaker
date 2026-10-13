from src.config.settings import BORDA_HEX
from src.core.editor_state import FRAMING_MODES
from src.core.preset_manager import PresetManager
from src.qt.compat import QT_AVAILABLE, qt_unavailable_error

if QT_AVAILABLE:
    from src.qt.compat import (
        QCheckBox,
        QColor,
        QComboBox,
        QIcon,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPixmap,
        QPushButton,
        QScrollArea,
        Qt,
        QVBoxLayout,
        QWidget,
    )


ANIMATION_OPTIONS = [
    "Nenhuma",
    "Rainbow",
    "Neon Pulsante",
    "Strobe (Pisca)",
    "Glitch",
    "Spin",
    "Flow",
]


if QT_AVAILABLE:
    class EditorTab(QWidget):
        def __init__(self, main_window, parent=None):
            super().__init__(parent)
            self.main_window = main_window

            outer_layout = QVBoxLayout(self)
            outer_layout.setContentsMargins(0, 0, 0, 0)

            scroll = QScrollArea(self)
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            outer_layout.addWidget(scroll)

            content = QWidget(scroll)
            scroll.setWidget(content)

            layout = QVBoxLayout(content)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(8)

            # ── Ajuste em lote ─────────────────────────────────────────────
            fit_group = QGroupBox("Ajuste em Lote")
            fit_layout = QVBoxLayout(fit_group)
            fit_layout.setSpacing(6)

            fit_row1 = QHBoxLayout()
            fit_row1.setSpacing(6)
            auto_fit_all_btn = QPushButton("Auto Fit")
            auto_fit_all_btn.setProperty("class", "secondary")
            auto_fit_all_btn.setToolTip("Auto fit em todas as imagens da lista  (Alt+B na imagem atual)")
            auto_fit_all_btn.clicked.connect(lambda: self.main_window.apply_adjustment_to_all("auto_fit"))
            smart_fit_all_btn = QPushButton("Inteligente")
            smart_fit_all_btn.setProperty("class", "secondary")
            smart_fit_all_btn.setToolTip(
                "Ajuste inteligente (centraliza o rosto) em todas as imagens  (Alt+F na imagem atual)"
            )
            smart_fit_all_btn.clicked.connect(lambda: self.main_window.apply_adjustment_to_all("intelligent_fit"))
            fit_row1.addWidget(auto_fit_all_btn, 1)
            fit_row1.addWidget(smart_fit_all_btn, 1)

            copy_frame_btn = QPushButton("Copiar Enquadramento para Todas")
            copy_frame_btn.setProperty("class", "secondary")
            copy_frame_btn.setToolTip("Aplica o enquadramento (pos+tamanho) da imagem atual a todas as outras")
            copy_frame_btn.clicked.connect(self.main_window.copy_framing_to_all)

            # M11: enquadramento aplicado a imagens ainda não enquadradas
            default_row = QHBoxLayout()
            default_row.setSpacing(6)
            default_label = QLabel("Padrão:")
            self.default_framing_combo = QComboBox()
            for mode, label in FRAMING_MODES.items():
                self.default_framing_combo.addItem(label, mode)
            self.default_framing_combo.setToolTip(
                "Enquadramento aplicado às imagens que ainda não foram ajustadas\n"
                "(ao abrir no editor e ao exportar). Não altera as já ajustadas."
            )
            self.default_framing_combo.currentIndexChanged.connect(self._on_default_framing_changed)
            default_row.addWidget(default_label)
            default_row.addWidget(self.default_framing_combo, 1)

            fit_layout.addLayout(fit_row1)
            fit_layout.addWidget(copy_frame_btn)
            fit_layout.addLayout(default_row)

            # ── Saída ──────────────────────────────────────────────────────
            save_group = QGroupBox("Saída")
            save_layout = QHBoxLayout(save_group)
            save_layout.setSpacing(6)

            # Só "Salvar Todas" é ação primária aqui — as demais são variações
            # do mesmo fluxo e ficam secundárias para não competirem visualmente.
            save_images_button = QPushButton("Salvar Todas")
            save_images_button.setToolTip("Salvar todas as imagens  (Ctrl+S)")
            save_images_button.clicked.connect(self.main_window.save_all_images)

            save_current_button = QPushButton("Atual")
            save_current_button.setProperty("class", "secondary")
            save_current_button.setToolTip("Salvar apenas a imagem atual  (Ctrl+Shift+S)")
            save_current_button.clicked.connect(self.main_window.save_current_image)

            save_zip_button = QPushButton("ZIP")
            save_zip_button.setProperty("class", "secondary")
            save_zip_button.setToolTip("Exportar todas como arquivo ZIP")
            save_zip_button.clicked.connect(self.main_window.save_zip)

            upload_button = QPushButton("ImgChest ↑")
            upload_button.setProperty("class", "secondary")
            upload_button.setToolTip("Upload para ImgChest e copiar comando Mudae")
            upload_button.clicked.connect(self.main_window.upload_to_imgchest)

            save_layout.addWidget(save_images_button, 2)
            save_layout.addWidget(save_current_button, 1)
            save_layout.addWidget(save_zip_button, 1)
            save_layout.addWidget(upload_button, 2)

            # ── Presets ────────────────────────────────────────────────────
            preset_group = QGroupBox("Presets")
            preset_layout = QVBoxLayout(preset_group)
            preset_layout.setSpacing(6)

            row_save = QHBoxLayout()
            row_save.setSpacing(6)
            self.preset_name_edit = QLineEdit()
            self.preset_name_edit.setPlaceholderText("Nome do preset")
            save_preset_button = QPushButton("Salvar")
            save_preset_button.setProperty("class", "secondary")
            save_preset_button.setFixedWidth(88)
            save_preset_button.setToolTip("Salvar borda, cor e animação atuais como preset")
            save_preset_button.clicked.connect(self._save_preset)
            row_save.addWidget(self.preset_name_edit, 1)
            row_save.addWidget(save_preset_button)

            # M11: partes opcionais do preset
            row_options = QHBoxLayout()
            row_options.setSpacing(10)
            self.preset_include_framing = QCheckBox("Enquadramento padrão")
            self.preset_include_framing.setToolTip("Salvar também o enquadramento padrão (auto fit/inteligente)")
            self.preset_include_blacklist = QCheckBox("Blacklist Danbooru")
            self.preset_include_blacklist.setToolTip("Salvar também as tags excluídas da busca online")
            row_options.addWidget(self.preset_include_framing)
            row_options.addWidget(self.preset_include_blacklist)
            row_options.addStretch(1)

            row_load = QHBoxLayout()
            row_load.setSpacing(6)
            self.preset_combo = QComboBox()
            self.preset_combo.setToolTip("Aplicar um preset salvo")
            self.preset_combo.currentTextChanged.connect(self._load_preset)
            delete_preset_button = QPushButton("Excluir")
            delete_preset_button.setFixedWidth(88)
            delete_preset_button.setProperty("class", "secondary")
            delete_preset_button.setToolTip("Excluir o preset selecionado")
            delete_preset_button.clicked.connect(self._delete_preset)
            row_load.addWidget(self.preset_combo, 1)
            row_load.addWidget(delete_preset_button)

            preset_layout.addLayout(row_save)
            preset_layout.addLayout(row_options)
            preset_layout.addLayout(row_load)

            layout.addWidget(fit_group)
            layout.addWidget(save_group)
            layout.addWidget(preset_group)
            layout.addStretch(1)

            self.refresh_presets()
            self.sync_default_framing_combo()

        @staticmethod
        def _swatch_icon(color):
            pixmap = QPixmap(14, 14)
            pixmap.fill(QColor(color))
            return QIcon(pixmap)

        def refresh_presets(self):
            manager = self.main_window.preset_manager
            self.preset_combo.blockSignals(True)
            self.preset_combo.clear()
            self.preset_combo.addItem("Selecione...")
            for name in manager.list_presets():
                # M11: amostra da cor da borda ao lado do nome
                color = PresetManager.swatch_color(manager.get_preset(name), BORDA_HEX)
                if color:
                    self.preset_combo.addItem(self._swatch_icon(color), name)
                else:
                    self.preset_combo.addItem(name)
            self.preset_combo.blockSignals(False)

        def refresh_from_state(self):
            """Called whenever editor_state changes externally. Syncs options bar."""
            self.main_window.refresh_options_bar()
            self.sync_default_framing_combo()

        def sync_default_framing_combo(self):
            index = self.default_framing_combo.findData(self.main_window.editor_state.default_framing)
            if index >= 0 and index != self.default_framing_combo.currentIndex():
                self.default_framing_combo.blockSignals(True)
                self.default_framing_combo.setCurrentIndex(index)
                self.default_framing_combo.blockSignals(False)

        def _on_default_framing_changed(self, _index):
            mode = self.default_framing_combo.currentData()
            if mode:
                self.main_window.set_default_framing(mode)

        def sync_from_options_bar(self):
            """No-op — state is driven by main_window options bar and editor_state."""
            pass

        def _save_preset(self):
            name = self.preset_name_edit.text().strip()
            if not name:
                self.main_window.show_warning("Preset", "Informe um nome para o preset.")
                return
            state = self.main_window.editor_state
            data = {
                "border_name": state.selected_borda,
                "border_color": state.custom_borda_hex,
                "animation_type": state.animation_type,
            }
            if self.preset_include_framing.isChecked():
                data["default_framing"] = state.default_framing
            if self.preset_include_blacklist.isChecked():
                data["danbooru_blacklist"] = self.main_window.app_config.get("danbooru_tag_blacklist", "") or ""
            self.main_window.preset_manager.add_preset(name, data)
            self.refresh_presets()
            self.preset_combo.setCurrentText(name)
            self.main_window.show_status(f"Preset '{name}' salvo.")

        def _load_preset(self, name):
            if not name or name == "Selecione...":
                return
            data = self.main_window.preset_manager.get_preset(name)
            if not data:
                return
            self.main_window.apply_preset(data)
            self.main_window.refresh_options_bar()

        def _delete_preset(self):
            name = self.preset_combo.currentText()
            if not name or name == "Selecione...":
                return
            if self.main_window.preset_manager.delete_preset(name):
                self.refresh_presets()
                self.main_window.show_status(f"Preset '{name}' removido.")
else:
    class EditorTab:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
