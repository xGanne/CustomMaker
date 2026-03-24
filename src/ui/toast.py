import logging

import customtkinter as ctk


logger = logging.getLogger(__name__)


class ToastNotification(ctk.CTkToplevel):
    def __init__(self, parent, title, message, kind="info"):
        super().__init__(parent)

        self.kind = kind
        if kind == "success":
            self.color = "#a6e3a1"
            self.text_color = "#1e1e2e"
            icon = "OK"
        elif kind == "error":
            self.color = "#f38ba8"
            self.text_color = "#1e1e2e"
            icon = "X"
        else:
            self.color = "#89b4fa"
            self.text_color = "#1e1e2e"
            icon = "i"

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color=self.color)

        w = 300
        h = 60
        px = parent.winfo_x() + parent.winfo_width() - w - 20
        py = parent.winfo_y() + parent.winfo_height() - h - 20
        self.geometry(f"{w}x{h}+{px}+{py}")

        self.grid_columnconfigure(1, weight=1)

        lbl_icon = ctk.CTkLabel(self, text=icon, font=("Arial", 18, "bold"), text_color=self.text_color)
        lbl_icon.grid(row=0, column=0, padx=10, pady=10, sticky="ns")

        frame_text = ctk.CTkFrame(self, fg_color="transparent")
        frame_text.grid(row=0, column=1, sticky="nsew", pady=5)

        lbl_title = ctk.CTkLabel(
            frame_text,
            text=title,
            font=("Arial", 12, "bold"),
            text_color=self.text_color,
            anchor="w",
        )
        lbl_title.pack(fill="x")

        lbl_msg = ctk.CTkLabel(frame_text, text=message, font=("Arial", 11), text_color=self.text_color, anchor="w")
        lbl_msg.pack(fill="x")

        self.alpha = 0.0
        self.attributes("-alpha", self.alpha)
        self.fade_in()

    def fade_in(self):
        if self.alpha < 1.0:
            self.alpha += 0.1
            self.attributes("-alpha", self.alpha)
            self.after(20, self.fade_in)
        else:
            self.after(3000, self.fade_out)

    def fade_out(self):
        if self.alpha > 0.0:
            self.alpha -= 0.1
            self.attributes("-alpha", self.alpha)
            self.after(20, self.fade_out)
        else:
            self.destroy()


def show_toast(parent, title, message, kind="info"):
    try:
        ToastNotification(parent, title, message, kind)
    except Exception as exc:
        logger.warning("Toast fallback (%s): %s - %s", kind, title, exc)
