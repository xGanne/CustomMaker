import tkinter as tk
from tkinter import ttk
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

class ProgressBarPopup:
    def __init__(self, parent, title="Processando...", maximum=100):
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.geometry("300x150")
        self.window.attributes('-topmost', True)
        self.window.protocol("WM_DELETE_WINDOW", lambda: None) # Prevent closing
        self.window.resizable(False, False)
        
        # Center the window
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() // 2) - 150
            y = parent.winfo_rooty() + (parent.winfo_height() // 2) - 75
            self.window.geometry(f"+{x}+{y}")
        except: pass
        
        self.window.configure(bg=COLORS["bg_dark"])

        self.label = ttk.Label(self.window, text="Iniciando...", anchor="center", style="TLabel")
        self.label.pack(pady=(20, 10), padx=20, fill="x")

        self.progress = ttk.Progressbar(self.window, mode='determinate', maximum=maximum)
        self.progress.pack(pady=10, padx=20, fill="x")

        self.window.transient(parent)
        self.window.grab_set()
        self.window.update()

    def update_progress(self, value, text=None):
        self.progress['value'] = value
        if text:
            self.label.config(text=text)
        self.window.update()

    def close(self):
        self.window.grab_release()
        self.window.destroy()
