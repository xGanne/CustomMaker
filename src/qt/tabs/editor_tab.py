from src.qt.compat import QT_AVAILABLE, qt_unavailable_error

if QT_AVAILABLE:
    from src.qt.compat import (
        QComboBox,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
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
            auto_fit_all_btn = QPushButton("Auto Fit — Todas")
            auto_fit_all_btn.clicked.connect(lambda: self.main_window.apply_adjustment_to_all("auto_fit"))
            smart_fit_all_btn = QPushButton("Inteligente — Todas")
            smart_fit_all_btn.clicked.connect(lambda: self.main_window.apply_adjustment_to_all("intelligent_fit"))
            fit_row1.addWidget(auto_fit_all_btn)
            fit_row1.addWidget(smart_fit_all_btn)

            copy_frame_btn = QPushButton("Copiar Enquadramento para Todas")
            copy_frame_btn.setProperty("class", "secondary")
            copy_frame_btn.setToolTip("Aplica o enquadramento (pos+tamanho) da imagem atual a todas as outras")
            copy_frame_btn.clicked.connect(self.main_window.copy_framing_to_all)

            fit_layout.addLayout(fit_row1)
            fit_layout.addWidget(copy_frame_btn)

            # ── Saída ──────────────────────────────────────────────────────
            save_group = QGroupBox("Saída")
            save_layout = QHBoxLayout(save_group)
            save_layout.setSpacing(6)

            save_images_button = QPushButton("Salvar")
            save_images_button.setToolTip("Salvar todas as imagens  (Ctrl+S)")
            save_images_button.clicked.connect(self.main_window.save_all_images)

            save_current_button = QPushButton("Atual")
            save_current_button.setProperty("class", "secondary")
            save_current_button.setToolTip("Salvar apenas a imagem atual  (Ctrl+Shift+S)")
            save_current_button.clicked.connect(self.main_window.save_current_image)

            save_zip_button = QPushButton("ZIP")
            save_zip_button.setToolTip("Exportar como arquivo ZIP")
            save_zip_button.clicked.connect(self.main_window.save_zip)

            upload_button = QPushButton("ImgChest ↑")
            upload_button.setToolTip("Upload para ImgChest e copiar comando Mudae")
            upload_button.clicked.connect(self.main_window.upload_to_imgchest)

            save_layout.addWidget(save_images_button)
            save_layout.addWidget(save_current_button)
            save_layout.addWidget(save_zip_button)
            save_layout.addWidget(upload_button)

            # ── Presets ────────────────────────────────────────────────────
            preset_group = QGroupBox("Presets")
            preset_layout = QVBoxLayout(preset_group)
            preset_layout.setSpacing(6)

            row_save = QHBoxLayout()
            row_save.setSpacing(6)
            self.preset_name_edit = QLineEdit()
            self.preset_name_edit.setPlaceholderText("Nome do preset")
            save_preset_button = QPushButton("Salvar")
            save_preset_button.setMaximumWidth(80)
            save_preset_button.clicked.connect(self._save_preset)
            row_save.addWidget(self.preset_name_edit)
            row_save.addWidget(save_preset_button)

            row_load = QHBoxLayout()
            row_load.setSpacing(6)
            self.preset_combo = QComboBox()
            self.preset_combo.currentTextChanged.connect(self._load_preset)
            delete_preset_button = QPushButton("Excluir")
            delete_preset_button.setMaximumWidth(80)
            delete_preset_button.setProperty("class", "secondary")
            delete_preset_button.clicked.connect(self._delete_preset)
            row_load.addWidget(self.preset_combo)
            row_load.addWidget(delete_preset_button)

            preset_layout.addLayout(row_save)
            preset_layout.addLayout(row_load)

            layout.addWidget(fit_group)
            layout.addWidget(save_group)
            layout.addWidget(preset_group)
            layout.addStretch(1)

            self.refresh_presets()

        def refresh_presets(self):
            presets = self.main_window.preset_manager.list_presets()
            self.preset_combo.blockSignals(True)
            self.preset_combo.clear()
            self.preset_combo.addItem("Selecione...")
            self.preset_combo.addItems(presets)
            self.preset_combo.blockSignals(False)

        def refresh_from_state(self):
            """Called whenever editor_state changes externally. Syncs options bar."""
            self.main_window.refresh_options_bar()

        def sync_from_options_bar(self):
            """No-op — state is driven by main_window options bar and editor_state."""
            pass

        def _save_preset(self):
            name = self.preset_name_edit.text().strip()
            if not name:
                self.main_window.show_warning("Preset", "Informe um nome para o preset.")
                return
            state = self.main_window.editor_state
            self.main_window.preset_manager.add_preset(
                name,
                {
                    "border_name": state.selected_borda,
                    "border_color": state.custom_borda_hex,
                    "animation_type": state.animation_type,
                },
            )
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
