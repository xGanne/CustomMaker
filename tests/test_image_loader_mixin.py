"""Tests for ImageLoaderMixin (cache LRU and undo stack)."""
import unittest
from collections import OrderedDict
from unittest.mock import MagicMock, patch

from PIL import Image


def _make_image(w=10, h=10, color="red"):
    return Image.new("RGBA", (w, h), color)


class _FakeLoader:
    """Minimal stub that includes only ImageLoaderMixin."""

    from src.qt.mixins.image_loader_mixin import ImageLoaderMixin

    class _Impl(ImageLoaderMixin):
        def __init__(self):
            self._preview_cache = OrderedDict()
            self._preview_cache_current_bytes = 0
            self._preview_cache_limit_bytes = 1024 * 1024  # 1 MB
            self.current_original_image = None

        def show_status(self, *_a, **_kw):
            pass

        def show_error(self, *_a, **_kw):
            pass

    def __new__(cls):
        return cls._Impl()


class TestPreviewCache(unittest.TestCase):
    def setUp(self):
        self.loader = _FakeLoader()

    def test_remember_and_get_copy(self):
        img = _make_image()
        self.loader._remember_preview_cache("/a.png", img)
        copy = self.loader._get_preview_cache_copy("/a.png")
        self.assertIsNotNone(copy)
        self.assertEqual(copy.size, img.size)
        copy.close()
        img.close()

    def test_missing_key_returns_none(self):
        self.assertIsNone(self.loader._get_preview_cache_copy("/missing.png"))

    def test_eviction_when_limit_exceeded(self):
        # 10x10 RGBA = 400 bytes each. Set limit to hold exactly 1 image.
        self.loader._preview_cache_limit_bytes = 450
        img_a = _make_image(color="red")
        img_b = _make_image(color="blue")
        self.loader._remember_preview_cache("/a.png", img_a)
        self.loader._remember_preview_cache("/b.png", img_b)
        # /a.png should have been evicted (LRU: oldest item)
        self.assertIsNone(self.loader._get_preview_cache_copy("/a.png"))
        copy = self.loader._get_preview_cache_copy("/b.png")
        self.assertIsNotNone(copy)
        copy.close()
        img_a.close()
        img_b.close()

    def test_clear_preview_cache_releases_all(self):
        for i in range(5):
            img = _make_image(color="red")
            self.loader._remember_preview_cache(f"/{i}.png", img)
            img.close()
        self.loader._clear_preview_cache()
        self.assertEqual(len(self.loader._preview_cache), 0)
        self.assertEqual(self.loader._preview_cache_current_bytes, 0)

    def test_estimate_bytes_rgba(self):
        img = _make_image(10, 10, "red")
        size = self.loader._estimate_image_bytes(img)
        self.assertEqual(size, 10 * 10 * 4)
        img.close()

    def test_estimate_bytes_none(self):
        self.assertEqual(self.loader._estimate_image_bytes(None), 0)


class TestUndoStack(unittest.TestCase):
    def setUp(self):
        from collections import OrderedDict
        self.loader = _FakeLoader()
        # Simulate minimal state needed for undo
        self.loader._undo_stacks = {}
        self.loader.current_path = "/img.png"
        self.loader.edited_images = {}

        from src.core.editor_state import EditorState
        self.loader.editor_state = EditorState()
        self.loader.editor_state.image_list = ["/img.png"]

        # Mock canvas and preview
        self.loader.image_canvas = MagicMock()
        self.loader._preview_cache_limit_bytes = 256 * 1024 * 1024

    def test_undo_stack_capped_at_20(self):
        img = _make_image()
        self.loader.editor_state.image_states["/img.png"] = {"pos": (0, 0), "size": (10, 10)}
        # Simulate get_active_image_copy returning a copy
        with patch.object(self.loader, "get_active_image_copy", return_value=img.copy()):
            for _ in range(25):
                self.loader.save_state_for_undo()
        stack = self.loader._undo_stacks.get("/img.png", [])
        self.assertLessEqual(len(stack), 20)
        img.close()
        for snapshot_img, *_ in stack:
            snapshot_img.close()

    def test_undo_empty_stack_shows_status(self):
        statuses = []
        self.loader.show_status = statuses.append
        self.loader.undo_current_image()
        self.assertTrue(any("desfazer" in s.lower() or "nada" in s.lower() for s in statuses))
