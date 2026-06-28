"""Tests for AdjustmentsMixin."""
import unittest
from collections import OrderedDict
from unittest.mock import MagicMock, patch

from PIL import Image


def _make_image(w=225, h=350):
    return Image.new("RGBA", (w, h), "white")


class _FakeAdjuster:
    """Minimal stub that includes only AdjustmentsMixin."""
    from src.qt.mixins.adjustments_mixin import AdjustmentsMixin

    class _Impl(AdjustmentsMixin):
        def __init__(self):
            from src.core.editor_state import EditorState
            from collections import OrderedDict
            self.editor_state = EditorState()
            self.editor_state.borda_pos = (0, 0)
            self.edited_images = {}
            self._preview_cache = OrderedDict()
            self._preview_cache_current_bytes = 0
            self._preview_cache_limit_bytes = 256 * 1024 * 1024
            self.current_path = None
            self.face_cascade = None
            self.image_canvas = MagicMock()
            self.task_runner = MagicMock()
            self._warnings = []
            self._infos = []
            self._statuses = []

        def show_warning(self, _t, msg):
            self._warnings.append(msg)

        def show_info(self, _t, msg):
            self._infos.append(msg)

        def show_status(self, msg, **_kw):
            self._statuses.append(msg)

        def get_active_image_copy(self):
            return None

        def save_state_for_undo(self):
            pass

        def run_task(self, *_a, **_kw):
            pass

        def _dispose_images(self, images):
            for img in images:
                if img:
                    try:
                        img.close()
                    except Exception:
                        pass

        def _get_preview_cache_copy(self, path):
            cached = self._preview_cache.get(path)
            if cached is None:
                return None
            return cached.copy()

        def refresh_current_canvas(self):
            pass

        def apply_auto_fit(self, push_undo=True):
            pass

    def __new__(cls):
        return cls._Impl()


class TestAdjustmentsMixin(unittest.TestCase):

    def test_copy_framing_no_current_path(self):
        adj = _FakeAdjuster()
        adj.current_path = None
        adj.copy_framing_to_all()
        self.assertTrue(any("selecionada" in w for w in adj._warnings))

    def test_copy_framing_no_state(self):
        adj = _FakeAdjuster()
        adj.current_path = "/a.png"
        adj.editor_state.image_list = ["/a.png", "/b.png"]
        adj.copy_framing_to_all()
        self.assertTrue(any("enquadramento" in w.lower() for w in adj._warnings))

    def test_copy_framing_propagates_to_all(self):
        adj = _FakeAdjuster()
        adj.current_path = "/a.png"
        adj.editor_state.image_list = ["/a.png", "/b.png", "/c.png"]
        adj.editor_state.set_image_state("/a.png", (10, 20), (100, 150))
        adj.copy_framing_to_all()
        self.assertEqual(adj.editor_state.image_states["/b.png"]["pos"], (10, 20))
        self.assertEqual(adj.editor_state.image_states["/c.png"]["size"], (100, 150))
        # current image should NOT be overwritten by itself
        self.assertEqual(adj.editor_state.image_states["/a.png"]["pos"], (10, 20))

    def test_apply_style_to_all_warns_empty_list(self):
        adj = _FakeAdjuster()
        adj.apply_style_to_all()
        self.assertTrue(any("nenhuma" in w.lower() for w in adj._warnings))

    def test_apply_style_sets_individual_border(self):
        adj = _FakeAdjuster()
        adj.editor_state.image_list = ["/a.png", "/b.png"]
        adj.editor_state.selected_borda = "Red"
        adj.apply_style_to_all()
        self.assertEqual(adj.editor_state.individual_bordas["/a.png"], "Red")
        self.assertEqual(adj.editor_state.individual_bordas["/b.png"], "Red")
