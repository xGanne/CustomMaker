import logging

from src.qt.compat import QT_AVAILABLE, qt_unavailable_error

if QT_AVAILABLE:
    from src.qt.compat import QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


logger = logging.getLogger(__name__)


if QT_AVAILABLE:
    class AiTab(QWidget):
        def __init__(self, main_window, parent=None):
            super().__init__(parent)
            self.main_window = main_window
            self.pipeline_manager = None

            layout = QVBoxLayout(self)
            self.info_label = QLabel(
                "Modo seguro ativo: a IA gera uma descrição textual da edição quando edição de imagem não está disponível."
            )
            self.info_label.setWordWrap(True)
            self.prompt_edit = QLineEdit()
            self.prompt_edit.setPlaceholderText("Ex: trocar roupa para uniforme azul, manter pose e estilo")
            self.apply_button = QPushButton("Gerar descrição com IA")
            self.apply_button.clicked.connect(self.on_apply_click)
            self.status_label = QLabel("")
            layout.addWidget(self.info_label)
            layout.addWidget(self.prompt_edit)
            layout.addWidget(self.apply_button)
            layout.addWidget(self.status_label)
            layout.addStretch(1)

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
            self.apply_button.setEnabled(False)
            self.status_label.setText("Processando...")

            def task_fn(_cancel_event, on_progress):
                return manager.apply_uniform(
                    image,
                    prompt_suffix=prompt,
                    strength=0.5,
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
