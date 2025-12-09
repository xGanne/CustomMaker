from tkinter import ttk
from src.config.settings import COLORS

def configure_styles():
    style = ttk.Style()
    style.theme_use('clam')
    
    style.configure("TFrame", background=COLORS["bg_dark"])
    
    style.configure("TButton",
                font=("Segoe UI", 10),
                background=COLORS["bg_light"],
                foreground=COLORS["text"],
                borderwidth=0,
                focuscolor=COLORS["accent"],
                relief="flat")
    
    style.map("TButton",
        background=[('active', COLORS["accent"]), ('pressed', COLORS["bg_medium"])],
        foreground=[('active', COLORS["bg_dark"]), ('pressed', COLORS["text"])])
    
    style.configure("Accent.TButton",
                background=COLORS["accent"],
                foreground=COLORS["bg_dark"])
    
    style.map("Accent.TButton",
        background=[('active', COLORS["accent"]), ('pressed', COLORS["text_dim"])],
        foreground=[('active', COLORS["bg_dark"]), ('pressed', COLORS["bg_dark"])])
    
    style.configure("TLabel",
                font=("Segoe UI", 10),
                background=COLORS["bg_dark"],
                foreground=COLORS["text"])
    
    style.configure("Title.TLabel",
                font=("Segoe UI", 12, "bold"),
                background=COLORS["bg_dark"],
                foreground=COLORS["accent"])
    
    style.configure("TSeparator",
                background=COLORS["bg_light"])
    
    style.configure("TCombobox",
                selectbackground=COLORS["accent"],
                fieldbackground=COLORS["bg_medium"],
                background=COLORS["bg_light"],
                foreground=COLORS["text"],
                arrowcolor=COLORS["text"]) 
    
    style.map('TCombobox',
        fieldbackground=[('readonly', COLORS["bg_medium"])],
        selectbackground=[('readonly', COLORS["accent"])],
        selectforeground=[('readonly', COLORS["bg_dark"])],
        foreground=[('readonly', COLORS["text"])])
    
    style.configure("Vertical.TScrollbar",
                background=COLORS["bg_medium"],
                troughcolor=COLORS["bg_dark"],
                arrowcolor=COLORS["text"])
