
import customtkinter as ctk
import tkinter as tk

class ToastNotification(ctk.CTkToplevel):
    def __init__(self, parent, title, message, kind="info"):
        super().__init__(parent)
        
        self.kind = kind
        
        # Colors
        if kind == "success":
            self.color = "#a6e3a1" # Green
            self.text_color = "#1e1e2e"
            icon = "✅"
        elif kind == "error":
            self.color = "#f38ba8" # Red
            self.text_color = "#1e1e2e"
            icon = "❌"
        else:
            self.color = "#89b4fa" # Blue
            self.text_color = "#1e1e2e"
            icon = "ℹ️"

        # Window Config
        self.overrideredirect(True) # Remove title bar
        self.attributes('-topmost', True)
        self.configure(fg_color=self.color)
        
        # Dimensions and Position
        w = 300
        h = 60
        
        # Position at bottom right of parent
        px = parent.winfo_x() + parent.winfo_width() - w - 20
        py = parent.winfo_y() + parent.winfo_height() - h - 20
        
        self.geometry(f"{w}x{h}+{px}+{py}")
        
        # Layout
        self.grid_columnconfigure(1, weight=1)
        
        lbl_icon = ctk.CTkLabel(self, text=icon, font=("Arial", 24), text_color=self.text_color)
        lbl_icon.grid(row=0, column=0, padx=10, pady=10, sticky="ns")
        
        frame_text = ctk.CTkFrame(self, fg_color="transparent")
        frame_text.grid(row=0, column=1, sticky="nsew", pady=5)
        
        lbl_title = ctk.CTkLabel(frame_text, text=title, font=("Arial", 12, "bold"), text_color=self.text_color, anchor="w")
        lbl_title.pack(fill="x")
        
        lbl_msg = ctk.CTkLabel(frame_text, text=message, font=("Arial", 11), text_color=self.text_color, anchor="w")
        lbl_msg.pack(fill="x")
        
        # Animation
        self.alpha = 0.0
        self.attributes('-alpha', self.alpha)
        self.fade_in()
        
    def fade_in(self):
        if self.alpha < 1.0:
            self.alpha += 0.1
            self.attributes('-alpha', self.alpha)
            self.after(20, self.fade_in)
        else:
            self.after(3000, self.fade_out) # Wait 3s then fade out
            
    def fade_out(self):
        if self.alpha > 0.0:
            self.alpha -= 0.1
            self.attributes('-alpha', self.alpha)
            self.after(20, self.fade_out)
        else:
            self.destroy()

def show_toast(parent, title, message, kind="info"):
    try:
        ToastNotification(parent, title, message, kind)
    except:
        # Fallback if parent is destroyed or error
        print(f"Toast Error: {title} - {message}")
