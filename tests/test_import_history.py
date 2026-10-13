import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src.core.import_history import ImportHistory


class TestImportHistory(unittest.TestCase):
    """Posts já importados são lembrados enquanto o arquivo existir."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.store = os.path.join(self.tmp, "imported_posts.json")
        self.image = os.path.join(self.tmp, "42.jpg")
        with open(self.image, "wb") as f:
            f.write(b"x")

    def test_record_save_and_reload(self):
        history = ImportHistory(self.store)
        history.record(42, self.image)
        history.save()
        self.assertEqual(ImportHistory(self.store).get("42"), self.image)

    def test_deleted_file_counts_as_not_imported(self):
        history = ImportHistory(self.store)
        history.record(42, self.image)
        os.remove(self.image)
        self.assertIsNone(history.get(42))

    def test_corrupted_file_starts_empty(self):
        with open(self.store, "w", encoding="utf-8") as f:
            f.write("{quebrado")
        self.assertIsNone(ImportHistory(self.store).get(42))

    def test_oldest_entries_are_dropped_beyond_the_limit(self):
        with patch("src.core.import_history.MAX_ENTRIES", 3):
            history = ImportHistory(self.store)
            for post_id in range(5):
                history.record(post_id, self.image)
            history.save()
            reloaded = ImportHistory(self.store)
        self.assertIsNone(reloaded.get(0))
        self.assertIsNone(reloaded.get(1))
        self.assertEqual(reloaded.get(4), self.image)

    def test_save_without_changes_does_not_write(self):
        ImportHistory(self.store).save()
        self.assertFalse(os.path.exists(self.store))


if __name__ == "__main__":
    unittest.main()
