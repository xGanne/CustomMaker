import os
import sys

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # In dev mode, we want to look in the 'assets' folder for assets
        # OR the current directory if it's a file relative to the script?
        # Since we moved assets to /assets, we should handle that.
        # Check if the file exists in 'assets' folder first.
        base_path = os.path.abspath(".")
        
    possible_path = os.path.join(base_path, relative_path)
    if os.path.exists(possible_path):
        return possible_path
        
    # Check in assets submodule if not found
    assets_path = os.path.join(base_path, "assets", relative_path)
    if os.path.exists(assets_path):
        return assets_path
        
    return possible_path
