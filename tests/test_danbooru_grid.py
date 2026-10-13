import importlib
import unittest


grid_module = importlib.import_module("src.qt.widgets.danbooru_grid")


class TestRatingColor(unittest.TestCase):
    """M5: cada rating do Danbooru tem uma cor de filete própria."""

    def test_known_ratings_have_distinct_colors(self):
        colors = {grid_module.rating_color({"rating": r}) for r in ("g", "s", "q", "e")}
        self.assertEqual(len(colors), 4)
        self.assertNotIn(None, colors)

    def test_rating_is_case_insensitive(self):
        self.assertEqual(grid_module.rating_color({"rating": "E"}), grid_module.RATING_COLORS["e"])

    def test_unknown_or_missing_rating_has_no_color(self):
        self.assertIsNone(grid_module.rating_color({"rating": "x"}))
        self.assertIsNone(grid_module.rating_color({}))
        self.assertIsNone(grid_module.rating_color(None))


class _NoNetworkClient:
    def download_image(self, _url):
        return None


@unittest.skipUnless(getattr(grid_module, "QT_AVAILABLE", False), "PySide6 not installed")
class TestRatingStripeRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compat = importlib.import_module("src.qt.compat")
        cls.compat = compat
        cls.app = compat.QApplication.instance() or compat.QApplication([])

    def test_card_left_edge_is_painted_with_rating_color(self):
        grid = grid_module.DanbooruResultsGrid(None, _NoNetworkClient())
        try:
            grid.resize(400, 300)
            grid.display_posts([{"id": 1, "rating": "e"}])
            grid.show()
            self.app.processEvents()

            item_rect = grid.visualItemRect(grid.item(0))
            image = grid.viewport().grab().toImage()
            stripe_x = item_rect.left() + 1 + grid_module._RatingStripeDelegate.STRIPE_WIDTH // 2
            pixel = image.pixelColor(stripe_x, item_rect.center().y())
            self.assertEqual(pixel.name().lower(), grid_module.RATING_COLORS["e"].lower())
        finally:
            grid.close()
            grid.deleteLater()


if __name__ == "__main__":
    unittest.main()
