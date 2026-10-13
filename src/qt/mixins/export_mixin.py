"""
ExportMixin — exportação e upload em lote.

Responsabilidades:
  • Salvar todas as imagens (ou apenas a atual) com bordas/animações aplicadas
  • Gerar arquivo ZIP das imagens processadas
  • Upload para ImgChest e geração do comando Mudae
  • Helpers de formatação e exibição de resultados de operações em lote
"""
import os


# Limite de caracteres de uma mensagem do Discord (sem Nitro)
DISCORD_MESSAGE_LIMIT = 2000


class ExportMixin:

    # ── Helpers de formatação ──────────────────────────────────────────────

    @staticmethod
    def _format_count(label, value):
        return f"{label}: {int(value or 0)}"

    @staticmethod
    def _format_path(label, path):
        return f"{label}: {path}" if path else None

    @staticmethod
    def _format_skipped(result):
        skipped = result.get("skipped") or []
        if not skipped:
            return None
        names = ", ".join(skipped[:5])
        suffix = "..." if len(skipped) > 5 else ""
        return f"Puladas (sem enquadramento possível): {len(skipped)} — {names}{suffix}"

    def _show_result_summary(self, title, lines, details=None, warning=False):
        from src.qt.compat import QMessageBox
        message = "\n".join(line for line in lines if line)
        if warning:
            self.show_warning(title, message)
        elif details:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Information)
            box.setWindowTitle(title)
            box.setText(message)
            box.setDetailedText("\n".join(details))
            box.exec()
        else:
            self.show_info(title, message)

    def _mark_work_exported(self, result):
        """M2: exportação bem-sucedida zera o aviso de 'trabalho não exportado'."""
        if not result.get("cancelled") and not result.get("errors"):
            self.editor_state.image_dirty.clear()

    # ── Exportação ────────────────────────────────────────────────────────

    def save_current_image(self):
        """M12: exporta apenas a imagem selecionada (Ctrl+Shift+S)."""
        if not self.current_path:
            self.show_warning("Salvar", "Nenhuma imagem selecionada.")
            return
        is_anim = self.editor_state.animation_type != "Nenhuma"
        ext = ".gif" if is_anim else ".png"
        suggested = os.path.splitext(os.path.basename(self.current_path))[0] + f"_custom{ext}"
        filter_text = "GIF (*.gif)" if is_anim else "PNG (*.png)"
        file_path = self.choose_save_file("Salvar imagem atual", filter_text, suggested_name=suggested)
        if not file_path:
            return
        source_path = self.current_path
        batch = self.batch_controller.frozen()

        def task_fn(_cancel_event, on_progress):
            if on_progress:
                on_progress(0, 1, "Exportando imagem atual...")
            result = batch.save_single_image(source_path, file_path)
            if on_progress:
                on_progress(1, 1, "Concluído.")
            return result

        def on_done(result):
            if result.get("status") == "success":
                self.show_status(f"Imagem exportada: {file_path}")
            else:
                self.show_error("Salvar", result.get("error") or "Falha ao exportar a imagem.")

        self.run_task("qt_save_current_image", "Exportando imagem", task_fn, on_done=on_done)

    def save_all_images(self):
        if not self.editor_state.image_list:
            self.show_warning("Salvar", "Nenhuma imagem carregada.")
            return
        target_dir = self.choose_directory("Selecione a pasta para salvar")
        if not target_dir:
            return

        batch = self.batch_controller.frozen()

        def task_fn(cancel_event, on_progress):
            return batch.save_all_images(
                target_dir,
                progress_callback=on_progress,
                cancel_event=cancel_event,
            )

        def on_done(result):
            self._mark_work_exported(result)
            lines = [
                "Exportação concluída.",
                self._format_count("Processadas", result.get("processed")),
                self._format_count("Erros", result.get("errors")),
                self._format_skipped(result),
                self._format_path("Destino", result.get("target_dir") or target_dir),
            ]
            self._show_result_summary(
                "Salvar",
                lines,
                warning=bool(result.get("errors") or result.get("skipped")),
            )

        self.run_task(
            "qt_save_all_images",
            "Salvando imagens",
            task_fn,
            on_done=on_done,
            maximum=max(1, len(self.editor_state.image_list)),
        )

    def save_zip(self):
        if not self.editor_state.image_list:
            self.show_warning("ZIP", "Nenhuma imagem carregada.")
            return
        file_path = self.choose_save_file("Salvar ZIP", "Arquivos ZIP (*.zip)")
        if not file_path:
            return

        batch = self.batch_controller.frozen()

        def task_fn(cancel_event, on_progress):
            return batch.save_zip(
                file_path,
                progress_callback=on_progress,
                cancel_event=cancel_event,
            )

        def on_done(result):
            self._mark_work_exported(result)
            lines = [
                "ZIP gerado com sucesso.",
                self._format_count("Arquivos escritos", result.get("written")),
                self._format_count("Processadas", result.get("processed")),
                self._format_count("Erros", result.get("errors")),
                self._format_skipped(result),
                self._format_path("Arquivo", result.get("zip_path") or file_path),
            ]
            self._show_result_summary(
                "ZIP",
                lines,
                warning=bool(result.get("errors") or result.get("skipped")),
            )

        self.run_task(
            "qt_save_zip",
            "Gerando ZIP",
            task_fn,
            on_done=on_done,
            maximum=max(1, len(self.editor_state.image_list)),
        )

    def upload_to_imgchest(self):
        if not self.editor_state.image_list:
            self.show_warning("Upload", "Nenhuma imagem carregada.")
            return
        if not getattr(self.uploader, "api_token", None) and not self.uploader.reload_token():
            self._show_missing_token_dialog()
            return
        from src.qt.compat import QInputDialog
        album_title, ok = QInputDialog.getText(self, "Upload ImgChest", "Título do álbum:")
        if not ok:
            return
        album_title = album_title.strip() or "CustomMaker"

        batch = self.batch_controller.frozen()

        def task_fn(cancel_event, on_progress):
            return batch.upload_to_imgchest(
                album_title,
                progress_callback=on_progress,
                cancel_event=cancel_event,
            )

        def on_done(result):
            self._mark_work_exported(result)
            links = result.get("links") or []
            errors = result.get("errors") or []
            lines = [
                "Upload finalizado.",
                self._format_count("Processadas", result.get("processed")),
                self._format_count("Arquivos enviados", result.get("uploaded")),
                self._format_count("Links retornados", len(links)),
                self._format_count("Erros", len(errors)),
                self._format_skipped(result),
            ]
            if errors:
                self._show_result_summary("Upload", lines, details=errors[:20], warning=not links)
            if links:
                self._show_links_dialog(album_title, links)
                if not errors:
                    self._show_result_summary("Upload", lines)
            elif not errors:
                self.show_warning("Upload", "Nenhum link retornado.")

        self.run_task(
            "qt_upload_imgchest",
            "Enviando para ImgChest",
            task_fn,
            on_done=on_done,
            maximum=max(1, len(self.editor_state.image_list)),
        )

    def _show_missing_token_dialog(self):
        """F6: explica o token ausente e oferece abrir o .env para edição."""
        from src.core.uploader import ENV_FILE, ENV_TEMPLATE
        from src.qt.compat import QMessageBox
        from src.utils.file_reveal import open_with_default_app

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Upload")
        box.setText("Token da API ImgChest não configurado.")
        box.setInformativeText(
            "Defina IMG_CHEST_API_TOKEN no arquivo .env com o seu token real "
            "(o valor 'seu_token_aqui' é apenas um modelo). Depois de salvar o "
            "arquivo, clique em ImgChest de novo — não precisa reiniciar.\n\n"
            f"Arquivo: {ENV_FILE}"
        )
        open_button = box.addButton("Abrir .env", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        if box.clickedButton() is not open_button:
            return
        if not os.path.exists(ENV_FILE):
            try:
                with open(ENV_FILE, "w", encoding="utf-8") as file_obj:
                    file_obj.write(ENV_TEMPLATE)
            except OSError as exc:
                self.show_error("Upload", f"Não foi possível criar o .env: {exc}")
                return
        if not open_with_default_app(ENV_FILE):
            self.show_error("Upload", f"Não foi possível abrir o arquivo:\n{ENV_FILE}")

    @staticmethod
    def mudae_command(title, links):
        """Comando do Mudae que adiciona as imagens à custom `title`."""
        return f"$ai {title} $\n" + " $\n".join(links)

    @classmethod
    def mudae_commands(cls, title, links, limit=DISCORD_MESSAGE_LIMIT):
        """Comando dividido em mensagens que cabem no limite do Discord.

        Com ~40 imagens o comando único passava de 2000 caracteres e o Discord
        recusava a mensagem. Cada parte é um $ai completo para a mesma custom.
        """
        parts, current = [], []
        for link in links:
            candidate = current + [link]
            if current and len(cls.mudae_command(title, candidate)) > limit:
                parts.append(cls.mudae_command(title, current))
                candidate = [link]
            current = candidate
        if current:
            parts.append(cls.mudae_command(title, current))
        return parts

    def _show_links_dialog(self, title, links):
        from src.qt.compat import (
            QGuiApplication, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QVBoxLayout, QWidget, Qt,
        )
        commands = self.mudae_commands(title, links)
        dialog = QWidget(self, Qt.Dialog)
        dialog.setWindowTitle("Links de Upload")
        dialog.resize(560, 440)
        layout = QVBoxLayout(dialog)
        if len(commands) > 1:
            hint = QLabel(
                f"{len(links)} imagens: o comando foi dividido em {len(commands)} mensagens "
                f"(limite de {DISCORD_MESSAGE_LIMIT} caracteres do Discord). Envie uma de cada vez."
            )
            hint.setWordWrap(True)
            layout.addWidget(hint)
        text = QPlainTextEdit(dialog)
        text.setReadOnly(True)
        text.setPlainText("\n\n".join(commands))
        layout.addWidget(text)

        buttons = QHBoxLayout()
        dialog.copy_buttons = []
        for index, command in enumerate(commands, start=1):
            label = "Copiar comando" if len(commands) == 1 else f"Copiar parte {index}/{len(commands)}"
            button = QPushButton(label, dialog)

            def copy_part(_checked=False, command=command, index=index):
                QGuiApplication.clipboard().setText(command)
                suffix = "" if len(commands) == 1 else f" (parte {index} de {len(commands)})"
                self.show_status(f"Comando copiado para a área de transferência{suffix}.")

            button.clicked.connect(copy_part)
            buttons.addWidget(button)
            dialog.copy_buttons.append(button)
        layout.addLayout(buttons)
        dialog.show()
        return dialog
