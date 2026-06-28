from src.config.settings import BORDA_HEX
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
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(12)

            flow_group = QGroupBox("Fluxo")
            flow_layout = QVBoxLayout(flow_group)
            flow_layout.setSpacing(8)

            load_button = QPushButton("Selecionar Pasta")
            load_button.clicked.connect(self.main_window.load_folder)
            paste_button = QPushButton("Colar da Área de Transferência")
            paste_button.clicked.connect(self.main_window.paste_image)
            undo_button = QPushButton("Desfazer")
            undo_button.clicked.connect(self.main_window.undo_current_image)
            auto_fit_button = QPushButton("Auto Fit")
            auto_fit_button.clicked.connect(self.main_window.apply_auto_fit)
            auto_fit_all_button = QPushButton("Auto Fit em Todas")
            auto_fit_all_button.clicked.connect(lambda: self.main_window.apply_adjustment_to_all("auto_fit"))
            smart_fit_button = QPushButton("Ajuste Inteligente")
            smart_fit_button.clicked.connect(self.main_window.apply_intelligent_fit)
            smart_fit_all_button = QPushButton("Ajuste Inteligente em Todas")
            smart_fit_all_button.clicked.connect(lambda: self.main_window.apply_adjustment_to_all("intelligent_fit"))

            flow_layout.addWidget(load_button)
            flow_layout.addWidget(paste_button)
            flow_layout.addWidget(undo_button)
            flow_layout.addWidget(auto_fit_button)
            flow_layout.addWidget(auto_fit_all_button)
            flow_layout.addWidget(smart_fit_button)
            flow_layout.addWidget(smart_fit_all_button)

            style_group = QGroupBox("Borda e Animação")
            style_layout = QVBoxLayout(style_group)
            style_layout.setSpacing(6)
            style_layout.addWidget(QLabel("Borda"))
            self.border_combo = QComboBox()
            self.border_combo.addItems(sorted(BORDA_HEX.keys()) + ["Cor Personalizada"])
            self.border_combo.currentTextChanged.connect(self._on_border_changed)
            self.custom_color_edit = QLineEdit()
            self.custom_color_edit.setPlaceholderText("#FFFFFF")
            self.custom_color_edit.textChanged.connect(self._on_custom_color_changed)
            self.pick_color_button = QPushButton("Pick Color")
            self.pick_color_button.clicked.connect(self.main_window.toggle_color_picker)
            style_layout.addWidget(self.border_combo)
            style_layout.addWidget(self.custom_color_edit)
            style_layout.addWidget(self.pick_color_button)
            style_layout.addWidget(QLabel("Animação"))
            self.animation_combo = QComboBox()
            self.animation_combo.addItems(ANIMATION_OPTIONS)
            self.animation_combo.currentTextChanged.connect(self._on_animation_changed)
            style_layout.addWidget(self.animation_combo)

            save_group = QGroupBox("Saída")
            save_layout = QVBoxLayout(save_group)
            save_layout.setSpacing(8)
            save_images_button = QPushButton("Salvar Imagens")
            save_images_button.clicked.connect(self.main_window.save_all_images)
            save_zip_button = QPushButton("Salvar ZIP")
            save_zip_button.clicked.connect(self.main_window.save_zip)
            upload_button = QPushButton("Upload ImgChest")
            upload_button.clicked.connect(self.main_window.upload_to_imgchest)
            save_layout.addWidget(save_images_button)
            save_layout.addWidget(save_zip_button)
            save_layout.addWidget(upload_button)

            preset_group = QGroupBox("Presets")
            preset_layout = QVBoxLayout(preset_group)
            preset_layout.setSpacing(10)
            row_save = QHBoxLayout()
            row_save.setSpacing(8)
            self.preset_name_edit = QLineEdit()
            self.preset_name_edit.setPlaceholderText("Nome do preset")
            save_preset_button = QPushButton("Salvar")
            save_preset_button.setMaximumWidth(110)
            save_preset_button.clicked.connect(self._save_preset)
            row_save.addWidget(self.preset_name_edit)
            row_save.addWidget(save_preset_button)

            row_load = QHBoxLayout()
            row_load.setSpacing(8)
            self.preset_combo = QComboBox()
            self.preset_combo.currentTextChanged.connect(self._load_preset)
            delete_preset_button = QPushButton("Excluir")
            delete_preset_button.setMaximumWidth(130)
            delete_preset_button.clicked.connect(self._delete_preset)
            row_load.addWidget(self.preset_combo)
            row_load.addWidget(delete_preset_button)

            preset_layout.addLayout(row_save)
            preset_layout.addLayout(row_load)

            self.hint_label = QLabel("Fluxo: selecionar pasta, ajustar, exportar, enviar ou gerar descrição com IA.")
            self.hint_label.setWordWrap(True)

            layout.addWidget(flow_group)
            layout.addWidget(style_group)
            layout.addWidget(save_group)
            layout.addWidget(preset_group)
            layout.addWidget(self.hint_label)
            layout.addStretch(1)

            self.refresh_presets()
            self.refresh_from_state()

        def refresh_presets(self):
            presets = self.main_window.preset_manager.list_presets()
            self.preset_combo.blockSignals(True)
            self.preset_combo.clear()
            self.preset_combo.addItem("Selecione...")
            self.preset_combo.addItems(presets)
            self.preset_combo.blockSignals(False)

        def refresh_from_state(self):
            state = self.main_window.editor_state
            self.border_combo.blockSignals(True)
            self.animation_combo.blockSignals(True)
            self.custom_color_edit.blockSignals(True)

            border_index = self.border_combo.findText(state.selected_borda)
            if border_index >= 0:
                self.border_combo.setCurrentIndex(border_index)
            self.animation_combo.setCurrentText(state.animation_type)
            self.custom_color_edit.setText(state.custom_borda_hex)
            self.custom_color_edit.setEnabled(state.selected_borda == "Cor Personalizada")

            self.border_combo.blockSignals(False)
            self.animation_combo.blockSignals(False)
            self.custom_color_edit.blockSignals(False)

        def _on_border_changed(self, value):
            self.main_window.editor_state.selected_borda = value
            self.main_window.ui_preferences.last_global_borda = value
            self.custom_color_edit.setEnabled(value == "Cor Personalizada")
            self.main_window.refresh_current_canvas()

        def _on_custom_color_changed(self, value):
            if value.startswith("#") and len(value) == 7:
                self.main_window.editor_state.custom_borda_hex = value
                self.main_window.refresh_current_canvas()

        def _on_animation_changed(self, value):
            self.main_window.editor_state.animation_type = value
            self.main_window.refresh_current_canvas()
            self.main_window.show_status(f"Animação selecionada: {value}")

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
            self.refresh_from_state()

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
