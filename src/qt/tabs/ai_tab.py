import logging

from src.qt.compat import QT_AVAILABLE, qt_unavailable_error

if QT_AVAILABLE:
    from src.qt.compat import (
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QSlider,
        QTextEdit,
        QVBoxLayout,
        QWidget,
        Qt,
    )


logger = logging.getLogger(__name__)


if QT_AVAILABLE:
    class AiTab(QWidget):
        def __init__(self, main_window, parent=None):
            super().__init__(parent)
            self.main_window = main_window
            self.pipeline_manager = None

            layout = QVBoxLayout(self)
            layout.setSpacing(8)

            # ── Status da pipeline ─────────────────────────────────────────
            self.info_label = QLabel(
                "Modo seguro ativo: a IA gera uma descrição textual da edição quando edição de imagem não está disponível."
            )
            self.info_label.setWordWrap(True)
            self.info_label.setStyleSheet("color: #7B879D; font-size: 11px;")
            layout.addWidget(self.info_label)

            # ── Prompt do usuário ──────────────────────────────────────────
            prompt_group = QGroupBox("Prompt")
            prompt_layout = QVBoxLayout(prompt_group)
            self.prompt_edit = QLineEdit()
            self.prompt_edit.setPlaceholderText("Ex: trocar roupa para uniforme azul, manter pose e estilo")
            prompt_layout.addWidget(self.prompt_edit)

            # Slider de intensidade
            strength_row = QHBoxLayout()
            strength_label = QLabel("Intensidade:")
            strength_label.setFixedWidth(80)
            self.strength_slider = QSlider(Qt.Horizontal)
            self.strength_slider.setMinimum(0)
            self.strength_slider.setMaximum(100)
            self.strength_slider.setValue(50)
            self.strength_slider.setTickInterval(10)
            self.strength_value_label = QLabel("50%")
            self.strength_value_label.setFixedWidth(36)
            self.strength_slider.valueChanged.connect(
                lambda v: self.strength_value_label.setText(f"{v}%")
            )
            strength_row.addWidget(strength_label)
            strength_row.addWidget(self.strength_slider)
            strength_row.addWidget(self.strength_value_label)
            prompt_layout.addLayout(strength_row)

            self.apply_button = QPushButton("Gerar descrição com IA")
            self.apply_button.clicked.connect(self.on_apply_click)
            prompt_layout.addWidget(self.apply_button)

            self.status_label = QLabel("")
            self.status_label.setStyleSheet("font-size: 11px; color: #7B879D;")
            prompt_layout.addWidget(self.status_label)

            layout.addWidget(prompt_group)

            # ── Instrução base (base prompt) ───────────────────────────────
            base_group = QGroupBox("Instrução Base da IA")
            base_layout = QVBoxLayout(base_group)
            base_hint = QLabel("Instrução enviada antes do seu prompt. Customizável.")
            base_hint.setWordWrap(True)
            base_hint.setStyleSheet("color: #7B879D; font-size: 11px;")
            self.base_prompt_edit = QTextEdit()
            self.base_prompt_edit.setMaximumHeight(90)
            self.base_prompt_edit.setPlainText(
                self.main_window.app_config.get("ai_base_prompt", "")
            )
            save_base_btn = QPushButton("Salvar instrução base")
            save_base_btn.setProperty("class", "secondary")
            save_base_btn.clicked.connect(self._save_base_prompt)
            base_layout.addWidget(base_hint)
            base_layout.addWidget(self.base_prompt_edit)
            base_layout.addWidget(save_base_btn)
            layout.addWidget(base_group)
            layout.addStretch(1)

        def _save_base_prompt(self):
            text = self.base_prompt_edit.toPlainText().strip()
            if not text:
                self.main_window.show_warning("IA", "A instrução base não pode estar vazia.")
                return
            self.main_window.app_config.set("ai_base_prompt", text)
            self.main_window.app_config.save()
            # força recriação do pipeline com o novo prompt
            self.pipeline_manager = None
            self.main_window.show_status("Instrução base da IA salva.")

        def get_pipeline(self):
            if self.pipeline_manager is None:
                from src.core.ai_pipeline import AIPipelineManager
                base_prompt = self.main_window.app_config.get("ai_base_prompt")
                self.pipeline_manager = AIPipelineManager(base_prompt=base_prompt)
                caps = self.pipeline_manager.get_capabilities()
                if caps.image_edit:
                    self.info_label.setText("IA com edição de imagem habilitada.")
                elif caps.text_only:
                    self.info_label.setText("IA em modo seguro: o resultado será textual por padrão.")
            return self.pipeline_manager

        def on_apply_click(self):
            image = self.main_window.get_active_image_copy()
            if image is None:
                self.main_window.show_warning("IA", "Carregue uma imagem primeiro.")
                return

            manager = self.get_pipeline()
            prompt = self.prompt_edit.text().strip()
            strength = self.strength_slider.value() / 100.0
            self.apply_button.setEnabled(False)
            self.status_label.setText("Processando...")

            def task_fn(_cancel_event, on_progress):
                return manager.apply_uniform(
                    image,
                    prompt_suffix=prompt,
                    strength=strength,
                    status_callback=lambda message: on_progress(0, 1, message),
                )

            def on_done(result):
                self.apply_button.setEnabled(True)
                if result.kind == "image" and result.image is not None:
                    self.main_window.set_edited_image_for_current(result.image)
                    self.status_label.setText("Imagem atualizada.")
                    self.main_window.show_info("IA", "Imagem atualizada pela IA.")
                    return
                if result.kind == "text":
                    self.status_label.setText("Concluído em modo seguro.")
                    self.main_window.show_info("Resultado da IA", result.text or "A IA não retornou descrição.")
                    return
                self.status_label.setText("Erro")
                self.main_window.show_error("IA", result.error_message or "Erro desconhecido.")

            def on_error(exc):
                logger.exception("Falha no processamento de IA: %s", exc)
                self.apply_button.setEnabled(True)
                self.status_label.setText("Erro")
                self.main_window.show_error("IA", str(exc))

            self.main_window.run_task("qt_ai_apply", "Processando IA", task_fn, on_done=on_done, on_error=on_error)
else:
    class AiTab:
        def __init__(self, *_args, **_kwargs):
            raise qt_unavailable_error()
