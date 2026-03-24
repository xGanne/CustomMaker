import logging
import threading
from tkinter import messagebox

import customtkinter as ctk

from src.core.ai_provider import AIResult
from src.ui.theme import FONT_BODY, FONT_TITLE, SURFACE_MUTED, TEXT_PRIMARY, TEXT_SECONDARY
from src.ui.widgets import ActionButtonPrimary, InlineHint, SectionCard


logger = logging.getLogger(__name__)


class AITab:
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app
        self.pipeline_manager = None

        self.create_widgets()

    def create_widgets(self):
        ctk.CTkLabel(self.parent, text="Estudio AI", font=FONT_TITLE, text_color=TEXT_PRIMARY).pack(pady=(12, 6))

        card = SectionCard(
            self.parent,
            title="Prompt de Uniforme",
            subtitle="A IA aplica um ajuste visual com base no prompt informado.",
        )
        card.pack(fill="x", padx=10, pady=(6, 10))

        self.info_label = InlineHint(
            card.body,
            text="Modo seguro ativo: a IA descreve a edicao quando nao ha suporte de image-edit.",
            text_color=TEXT_SECONDARY,
            wraplength=320,
        )
        self.info_label.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(card.body, text="Detalhes adicionais (prompt):", anchor="w", text_color=TEXT_PRIMARY, font=FONT_BODY).pack(fill="x")
        self.prompt_entry = ctk.CTkEntry(
            card.body,
            placeholder_text="Ex: cabelo loiro, olhos azuis",
            fg_color=SURFACE_MUTED,
            border_color="#3A465D",
            text_color=TEXT_PRIMARY,
            font=FONT_BODY,
            height=34,
        )
        self.prompt_entry.pack(fill="x", pady=(0, 12))

        self.btn_apply = ActionButtonPrimary(
            card.body,
            text="Aplicar Prompt de Uniforme",
            command=self.on_apply_click,
        )
        self.btn_apply.pack(fill="x")

        self.status_label = ctk.CTkLabel(card.body, text="", text_color=TEXT_SECONDARY, font=FONT_BODY)
        self.status_label.pack(pady=(10, 0))

    def get_pipeline(self):
        if not self.pipeline_manager:
            from src.core.ai_pipeline import AIPipelineManager

            self.pipeline_manager = AIPipelineManager()
            caps = self.pipeline_manager.get_capabilities()
            if caps.image_edit:
                self.info_label.configure(text="IA com edicao de imagem habilitada.")
            elif caps.text_only:
                self.info_label.configure(
                    text="IA em modo seguro: o resultado sera textual (descricao/prompt), sem alterar a imagem automaticamente."
                )
        return self.pipeline_manager

    def on_apply_click(self):
        if not self.app.user_image and not self.app.original_image:
            messagebox.showwarning("Aviso", "Carregue uma imagem primeiro.")
            return

        image_to_process = self.app.user_image if self.app.user_image else self.app.original_image
        if not image_to_process:
            return

        self.btn_apply.configure(state="disabled", text="Processando...")
        self.status_label.configure(text="Iniciando IA...")

        prompt = self.prompt_entry.get()
        strength = 0.5

        threading.Thread(target=self._run_ai_thread, args=(image_to_process, prompt, strength), daemon=True).start()

    def _run_ai_thread(self, image, prompt, strength):
        try:
            mgr = self.get_pipeline()

            def update_status(msg):
                self.app.root.after(0, lambda: self.status_label.configure(text=msg))

            result = mgr.apply_uniform(
                image,
                prompt_suffix=prompt,
                strength=strength,
                status_callback=update_status,
            )
            self.app.root.after(0, lambda: self._on_result(result))
        except Exception as exc:
            logger.exception("Falha no thread de IA: %s", exc)
            self.app.root.after(0, lambda: self._on_error(str(exc)))

    def _on_result(self, result: AIResult):
        self.btn_apply.configure(state="normal", text="Aplicar Prompt de Uniforme")

        if result.kind == "image" and result.image is not None:
            self.status_label.configure(text="Concluido!")
            self.app.save_current_image_state()
            self.app.user_image = result.image
            self.app.user_image_pos = (
                (self.app.canvas.winfo_width() - result.image.width) // 2,
                (self.app.canvas.winfo_height() - result.image.height) // 2,
            )
            self.app.update_canvas()
            self.app.status_var.set("AI: imagem atualizada com sucesso.")
            messagebox.showinfo("Sucesso", "Imagem atualizada pela IA.")
            return

        if result.kind == "text":
            self.status_label.configure(text="Concluido (modo seguro).")
            text = result.text or "A IA nao retornou descricao."
            messagebox.showinfo("Resultado AI (Texto)", text)
            self.app.status_var.set("AI: descricao gerada em modo seguro.")
            return

        self._on_error(result.error_message or "Erro desconhecido no processamento de IA.")

    def _on_error(self, error_msg):
        self.btn_apply.configure(state="normal", text="Aplicar Prompt de Uniforme")
        self.status_label.configure(text="Erro")
        messagebox.showerror("Erro AI", f"Falha no processamento: {error_msg}")
