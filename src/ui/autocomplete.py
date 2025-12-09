import tkinter as tk
import customtkinter as ctk
import threading
from tkinter import messagebox

class DanbooruAutocomplete:
    def __init__(self, entry_widget, root, client):
        self.entry = entry_widget
        self.root = root
        self.client = client
        self.popup = None
        self.listbox = None
        self.after_id = None
        
        self.entry.bind("<KeyRelease>", self.on_key_release)
        self.entry.bind("<FocusOut>", self.on_focus_out)
        self.entry.bind("<Down>", self.focus_list)

    def on_key_release(self, event):
        # Ignore navigation keys
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab"): return
        
        if self.after_id:
            self.root.after_cancel(self.after_id)
        self.after_id = self.root.after(300, self.fetch_suggestions)

    def fetch_suggestions(self):
        # Simple word detection
        cursor_pos = self.entry.index(tk.INSERT)
        full_text = self.entry.get()
        
        # Simplified: Autocomplete the last word if cursor is at end, or use simple split
        # We try to grab the word immediately before the cursor
        try:
            text_upto_cursor = full_text[:cursor_pos]
            if not text_upto_cursor:
                self.hide_popup()
                return

            words = text_upto_cursor.split(' ')
            current_word = words[-1]
            
            if len(current_word) < 2:
                self.hide_popup()
                return

            def task():
                suggestions = self.client.fetch_tags(current_word)
                self.root.after(0, lambda: self.show_suggestions(suggestions, current_word))
            
            threading.Thread(target=task, daemon=True).start()

        except Exception as e:
            print(e)
            self.hide_popup()

    def show_suggestions(self, tags, query_word):
        if not tags:
            self.hide_popup()
            return
            
        if not self.popup:
            self.popup = ctk.CTkToplevel(self.root)
            self.popup.wm_overrideredirect(True)
            self.popup.attributes("-topmost", True)
            
            # Simple Frame with Listbox
            self.listbox = tk.Listbox(self.popup, bg="#2b2b2b", fg="#ffffff", 
                                      borderwidth=0, highlightthickness=0, font=("Segoe UI", 10))
            self.listbox.pack(fill="both", expand=True)
            self.listbox.bind("<<ListboxSelect>>", lambda e: self.apply_selection(query_word))
            self.listbox.bind("<Return>", lambda e: self.apply_selection(query_word))
        
        self.listbox.delete(0, tk.END)
        for tag in tags:
            self.listbox.insert(tk.END, tag)
            
        # Position Popup
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height()
        w = self.entry.winfo_width()
        h = min(200, len(tags)*20)
        self.popup.geometry(f"{w}x{h}+{x}+{y}")
        self.popup.deiconify()

    def hide_popup(self):
        if self.popup:
            self.popup.destroy()
            self.popup = None

    def apply_selection(self, query_word=None):
        if not self.popup or not self.listbox.curselection(): return
        
        selection = self.listbox.get(self.listbox.curselection())
        
        full_text = self.entry.get()
        cursor_pos = self.entry.index(tk.INSERT)
        
        text_before = full_text[:cursor_pos]
        text_after = full_text[cursor_pos:]
        
        # Dynamically find the start of the word being typed to avoid stale query issues
        last_space_index = text_before.rfind(' ')
        
        if last_space_index == -1:
            # First word
            new_text_before = selection + " "
        else:
            # Provide text up to space + selection + space
            new_text_before = text_before[:last_space_index+1] + selection + " "
             
        final_text = new_text_before + text_after
        
        self.entry.delete(0, tk.END)
        self.entry.insert(0, final_text)
        
        self.entry.icursor(len(new_text_before))
        
        self.hide_popup()
        self.entry.focus_set()

    def on_focus_out(self, event):
        self.root.after(150, self.hide_popup)

    def focus_list(self, event):
        if self.popup:
            self.listbox.focus_set()
            self.listbox.selection_set(0)
