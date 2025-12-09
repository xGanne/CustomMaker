import tkinter as tk
from src.config.settings import COLORS

class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.id = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event=None):
        self.id = self.widget.after(500, self._show_tooltip) # Atraso de 500ms

    def _show_tooltip(self):
        if self.tooltip_window:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True) # Remove borda e título
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(self.tooltip_window, text=self.text, background=COLORS["bg_light"],
                        foreground=COLORS["text"], relief=tk.SOLID, borderwidth=1,
                        font=("Segoe UI", 9), padx=5, pady=2)
        label.pack()

    def hide_tooltip(self, event=None):
        if self.id:
            self.widget.after_cancel(self.id)
        if self.tooltip_window:
            self.tooltip_window.destroy()
        self.tooltip_window = None
