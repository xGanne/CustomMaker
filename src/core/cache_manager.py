import os
import hashlib
import time
import threading

class CacheManager:
    def __init__(self, cache_dir=".cache", max_age_days=3):
        self.cache_dir = cache_dir
        self.max_age_days = max_age_days
        
        if not os.path.exists(self.cache_dir):
            try:
                os.makedirs(self.cache_dir)
            except: pass
            
        # Run cleanup on startup in a separate thread
        threading.Thread(target=self.cleanup, daemon=True).start()

    def _get_path(self, key):
        # Use MD5 hash of key (url) as filename to avoid invalid chars
        hashed = hashlib.md5(key.encode('utf-8')).hexdigest()
        return os.path.join(self.cache_dir, hashed)

    def get(self, key):
        path = self._get_path(key)
        if os.path.exists(path):
            try:
                # Update modification time to keep it fresh so it doesn't get deleted
                os.utime(path, None)
                with open(path, "rb") as f:
                    return f.read()
            except:
                return None
        return None

    def set(self, key, data):
        if not data: return
        try:
            path = self._get_path(key)
            with open(path, "wb") as f:
                f.write(data)
        except: pass

    def cleanup(self):
        try:
            now = time.time()
            cutoff = now - (self.max_age_days * 86400)
            
            for fname in os.listdir(self.cache_dir):
                path = os.path.join(self.cache_dir, fname)
                try:
                    mtime = os.path.getmtime(path)
                    if mtime < cutoff:
                        os.remove(path)
                        print(f"DEBUG: Cache cleaned {fname}")
                except: pass
        except: pass
