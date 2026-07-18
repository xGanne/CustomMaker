"""
ExportMixin — exportação e upload em lote.

Responsabilidades:
  • Salvar todas as imagens em pasta com bordas/animações aplicadas
  • Gerar arquivo ZIP das imagens processadas
  • Upload para ImgChest e geração do comando Mudae
  • Helpers de formatação e exibição de resultados de operações em lote
"""


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

    # ── Exportação ────────────────────────────────────────────────────────

    def save_all_images(self):
        if not self.editor_state.image_list:
            self.show_warning("Salvar", "Nenhuma imagem carregada.")
            return
        target_dir = self.choose_directory("Selecione a pasta para salvar")
        if not target_dir:
            return

        def task_fn(cancel_event, on_progress):
            return self.batch_controller.save_all_images(
                target_dir,
                progress_callback=on_progress,
                cancel_event=cancel_event,
            )

        def on_done(result):
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

        def task_fn(cancel_event, on_progress):
            return self.batch_controller.save_zip(
                file_path,
                progress_callback=on_progress,
                cancel_event=cancel_event,
            )

        def on_done(result):
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
        from src.qt.compat import QInputDialog
        album_title, ok = QInputDialog.getText(self, "Upload ImgChest", "Título do álbum:")
        if not ok:
            return
        album_title = album_title.strip() or "CustomMaker"

        def task_fn(cancel_event, on_progress):
            return self.batch_controller.upload_to_imgchest(
                album_title,
                progress_callback=on_progress,
                cancel_event=cancel_event,
            )

        def on_done(result):
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

    def _show_links_dialog(self, title, links):
        from src.qt.compat import QGuiApplication, QPushButton, QPlainTextEdit, QVBoxLayout, QWidget, Qt
        dialog = QWidget(self, Qt.Dialog)
        dialog.setWindowTitle("Links de Upload")
        dialog.resize(540, 420)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit(dialog)
        text.setReadOnly(True)
        text.setPlainText("\n".join(links))
        copy_button = QPushButton("Copiar comando", dialog)

        def copy_links():
            command = f"$ai {title} $\n" + " $\n".join(links)
            QGuiApplication.clipboard().setText(command)
            self.show_status("Comando copiado para a área de transferência.")

        copy_button.clicked.connect(copy_links)
        layout.addWidget(text)
        layout.addWidget(copy_button)
        dialog.show()
