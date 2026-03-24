import os
import tempfile
import time
import unittest

from src.core.cache_manager import CacheManager


class TestCacheManager(unittest.TestCase):
    def test_evicts_oldest_file_when_size_limit_exceeded(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = CacheManager(cache_dir=tmp, max_age_days=30, max_disk_size_mb=0.0006)
            first_data = b"a" * 350
            second_data = b"b" * 350

            cache.set("first", first_data)
            time.sleep(0.02)  # ensure mtime ordering for LRU by mtime
            cache.set("second", second_data)
            cache.cleanup()

            self.assertIsNone(cache.get("first"))
            self.assertEqual(cache.get("second"), second_data)

    def test_cleanup_still_removes_expired_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = CacheManager(cache_dir=tmp, max_age_days=1, max_disk_size_mb=10)
            old_data = b"old-data"
            new_data = b"new-data"

            cache.set("old", old_data)
            cache.set("new", new_data)

            old_path = cache._get_path("old")
            expired_time = time.time() - (3 * 86400)
            os.utime(old_path, (expired_time, expired_time))

            cache.cleanup()

            self.assertIsNone(cache.get("old"))
            self.assertEqual(cache.get("new"), new_data)
