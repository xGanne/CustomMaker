import logging
import tkinter as tk

import customtkinter as ctk

from src.ui.theme import (
    FONT_BODY,
    FONT_CAPTION,
    FONT_SECTION,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    button_style,
    card_style,
)


logger = logging.getLogger(__name__)


class SectionCard(ctk.CTkFrame):
    def __init__(self, parent, title=None, subtitle=None, *args, **kwargs):
        style = card_style("default")
        style.update(kwargs)
        super().__init__(parent, *args, **style)

        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", padx=12, pady=(10, 4))

        if title:
            self.title_label = ctk.CTkLabel(self.header, text=title, font=FONT_SECTION, text_color=TEXT_PRIMARY, anchor="w")
            self.title_label.pack(fill="x")
        else:
            self.title_label = None

        if subtitle:
            self.subtitle_label = ctk.CTkLabel(
                self.header,
                text=subtitle,
                font=FONT_CAPTION,
                text_color=TEXT_SECONDARY,
                anchor="w",
                justify="left",
                wraplength=300,
            )
            self.subtitle_label.pack(fill="x", pady=(2, 0))
        else:
            self.subtitle_label = None

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=12, pady=(0, 12))


class ActionButtonPrimary(ctk.CTkButton):
    def __init__(self, parent, *args, **kwargs):
        style = button_style("primary")
        style.update(kwargs)
        super().__init__(parent, *args, **style)


class ActionButtonSecondary(ctk.CTkButton):
    def __init__(self, parent, kind="secondary", *args, **kwargs):
        style = button_style(kind)
        style.update(kwargs)
        super().__init__(parent, *args, **style)


class InlineHint(ctk.CTkLabel):
    def __init__(self, parent, text, *args, **kwargs):
        kwargs.setdefault("text_color", TEXT_MUTED)
        kwargs.setdefault("font", FONT_CAPTION)
        kwargs.setdefault("justify", "left")
        kwargs.setdefault("anchor", "w")
        kwargs.setdefault("wraplength", 300)
        super().__init__(parent, text=text, *args, **kwargs)


class EmptyStatePanel(ctk.CTkFrame):
    def __init__(self, parent, title, description, action_text=None, action_command=None, *args, **kwargs):
        style = card_style("default")
        style.update(kwargs)
        super().__init__(parent, *args, **style)

        ctk.CTkLabel(self, text=title, font=FONT_SECTION, text_color=TEXT_PRIMARY).pack(pady=(16, 6), padx=12)
        ctk.CTkLabel(
            self,
            text=description,
            font=FONT_BODY,
            text_color=TEXT_SECONDARY,
            justify="center",
            wraplength=300,
        ).pack(pady=(0, 12), padx=12)

        if action_text and action_command:
            ActionButtonPrimary(self, text=action_text, command=action_command).pack(pady=(0, 16), padx=12)


class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.after_id = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, _event=None):
        self.after_id = self.widget.after(500, self._show_tooltip)

    def _show_tooltip(self):
        if self.tooltip_window:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tooltip_window = ctk.CTkToplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.geometry(f"+{x}+{y}")
        label = ctk.CTkLabel(
            self.tooltip_window,
            text=self.text,
            fg_color="#333333",
            text_color="#ffffff",
            corner_radius=6,
            padx=10,
            pady=5,
        )
        label.pack()

    def hide_tooltip(self, _event=None):
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None


class ProgressBarPopup:
    def __init__(self, parent, title="Processando...", maximum=100, on_cancel=None):
        self.window = ctk.CTkToplevel(parent)
        self.window.title(title)
        self.window.geometry("340x170")
        self.window.attributes("-topmost", True)
        self.window.resizable(False, False)
        self.on_cancel = on_cancel

        if on_cancel:
            self.window.protocol("WM_DELETE_WINDOW", self._handle_cancel)
        else:
            self.window.protocol("WM_DELETE_WINDOW", lambda: None)

        try:
            x = parent.winfo_rootx() + (parent.winfo_width() // 2) - 170
            y = parent.winfo_rooty() + (parent.winfo_height() // 2) - 85
            self.window.geometry(f"+{x}+{y}")
        except Exception as exc:
            logger.debug("Falha ao centralizar popup: %s", exc)

        self.label = ctk.CTkLabel(self.window, text="Iniciando...", anchor="center")
        self.label.pack(pady=(20, 10), padx=20, fill="x")

        self.progress = ctk.CTkProgressBar(self.window)
        self.progress.set(0)
        self.progress.pack(pady=10, padx=20, fill="x")

        if on_cancel:
            self.cancel_btn = ctk.CTkButton(self.window, text="Cancelar", command=self._handle_cancel, width=90)
            self.cancel_btn.pack(pady=(0, 8))
        else:
            self.cancel_btn = None

        self.maximum = max(1, maximum)
        self.window.grab_set()
        self.window.update_idletasks()

    def _handle_cancel(self):
        try:
            if self.on_cancel:
                self.on_cancel()
        finally:
            self.close()

    def update_progress(self, value, text=None):
        norm_value = value / self.maximum if self.maximum > 0 else 0
        self.progress.set(max(0.0, min(1.0, norm_value)))
        if text:
            self.label.configure(text=text)
        self.window.update_idletasks()

    def close(self):
        if self.window.winfo_exists():
            try:
                self.window.grab_release()
            except tk.TclError:
                pass
            self.window.destroy()
