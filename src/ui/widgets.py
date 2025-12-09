import tkinter as tk
import customtkinter as ctk

class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.id = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event=None):
        self.id = self.widget.after(500, self._show_tooltip) 

    def _show_tooltip(self):
        if self.tooltip_window: return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        
        # CTk doesn't support Toplevel overrideredirect nicely usually, resorting to tk.Toplevel for tooltip
        # but using CTkLabel inside
        self.tooltip_window = ctk.CTkToplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.geometry(f"+{x}+{y}")
        
        label = ctk.CTkLabel(self.tooltip_window, text=self.text, fg_color="#333333", text_color="#ffffff",
                             corner_radius=6, padx=10, pady=5)
        label.pack()

    def hide_tooltip(self, event=None):
        if self.id: self.widget.after_cancel(self.id)
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

class ProgressBarPopup:
    def __init__(self, parent, title="Processando...", maximum=100):
        self.window = ctk.CTkToplevel(parent)
        self.window.title(title)
        self.window.geometry("300x150")
        self.window.attributes('-topmost', True)
        self.window.protocol("WM_DELETE_WINDOW", lambda: None)
        self.window.resizable(False, False)
        
        # Center
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() // 2) - 150
            y = parent.winfo_rooty() + (parent.winfo_height() // 2) - 75
            self.window.geometry(f"+{x}+{y}")
        except: pass
        
        self.label = ctk.CTkLabel(self.window, text="Iniciando...", anchor="center")
        self.label.pack(pady=(20, 10), padx=20, fill="x")

        self.progress = ctk.CTkProgressBar(self.window)
        self.progress.set(0)
        self.progress.pack(pady=10, padx=20, fill="x")
        
        self.maximum = maximum
        self.window.grab_set()
        self.window.update()

    def update_progress(self, value, text=None):
        # CTkProgressBar uses 0.0 to 1.0
        norm_value = value / self.maximum if self.maximum > 0 else 0
        self.progress.set(norm_value)
        if text:
            self.label.configure(text=text)
        self.window.update()

    def close(self):
        self.window.grab_release()
        self.window.destroy()
