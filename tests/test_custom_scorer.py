import unittest

from PIL import Image, ImageDraw

from src.config.settings import BORDA_HEIGHT, BORDA_WIDTH
from src.core.custom_scorer import (
    combined_score,
    metadata_score,
    rank_posts_by_metadata,
    visual_score,
)


def _post(tag_string="", width=None, height=None, score=0, fav_count=0):
    return {
        "tag_string": tag_string,
        "image_width": width,
        "image_height": height,
        "score": score,
        "fav_count": fav_count,
    }


class _FakeCascade:
    """Stub replacing cv2.CascadeClassifier for deterministic tests."""

    def __init__(self, faces):
        self._faces = faces

    def detectMultiScale(self, *_args, **_kwargs):
        return self._faces


class TestMetadataScore(unittest.TestCase):
    def test_solo_portrait_scores_higher_than_group_comic(self):
        good = _post("solo upper_body looking_at_viewer", width=225, height=350)
        bad = _post("multiple_girls comic text", width=1200, height=400)
        self.assertGreater(metadata_score(good), metadata_score(bad))

    def test_aspect_ratio_close_to_target_scores_higher(self):
        # BORDA_WIDTH/BORDA_HEIGHT target ratio
        close = _post(width=BORDA_WIDTH, height=BORDA_HEIGHT)
        wide = _post(width=1600, height=300)
        self.assertGreater(metadata_score(close), metadata_score(wide))

    def test_missing_dimensions_do_not_crash(self):
        post = _post(width=None, height=None)
        self.assertIsInstance(metadata_score(post), float)

    def test_popularity_is_a_small_nudge_not_dominant(self):
        low_pop = _post("solo", score=0, fav_count=0)
        high_pop = _post("solo", score=10000, fav_count=10000)
        diff = metadata_score(high_pop) - metadata_score(low_pop)
        # popularity should nudge, not swing the score by double digits
        self.assertGreater(diff, 0)
        self.assertLess(diff, 5)

    def test_rank_posts_by_metadata_orders_descending(self):
        posts = [
            _post("multiple_girls comic"),
            _post("solo portrait", width=BORDA_WIDTH, height=BORDA_HEIGHT),
            _post(),
        ]
        ranked = rank_posts_by_metadata(posts)
        scores = [metadata_score(p) for p in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))


class TestVisualScore(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGB", (400, 600), "white")
        ImageDraw.Draw(self.image)

    def test_no_face_detected_is_penalized(self):
        cascade = _FakeCascade([])
        self.assertLess(visual_score(self.image, cascade), 0)

    def test_multiple_faces_penalized_more_than_single_tiny_face(self):
        single_tiny = _FakeCascade([(10, 10, 5, 5)])
        multiple = _FakeCascade([(10, 10, 50, 50), (200, 10, 50, 50)])
        self.assertLess(visual_score(self.image, multiple), visual_score(self.image, single_tiny))

    def test_well_proportioned_single_face_scores_best(self):
        # face covering ~15% of the frame — a believable portrait crop
        good_face = _FakeCascade([(100, 100, 150, 150)])
        tiny_face = _FakeCascade([(10, 10, 8, 8)])
        self.assertGreater(visual_score(self.image, good_face), visual_score(self.image, tiny_face))

    def test_no_cascade_returns_neutral_zero(self):
        self.assertEqual(visual_score(self.image, None), 0.0)

    def test_no_image_returns_neutral_zero(self):
        self.assertEqual(visual_score(None, _FakeCascade([])), 0.0)


class TestCombinedScore(unittest.TestCase):
    def test_combined_adds_visual_bonus_to_metadata(self):
        post = _post("solo", width=BORDA_WIDTH, height=BORDA_HEIGHT)
        base = metadata_score(post)
        self.assertAlmostEqual(combined_score(post, visual_bonus=1.5), base + 1.5)
        self.assertAlmostEqual(combined_score(post), base)


if __name__ == "__main__":
    unittest.main()
