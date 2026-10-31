import unittest

from PIL import Image

from src.core.color_adjustments import apply_all, apply_tone, cache_token, is_neutral, normalize


def _gradient(width=200, height=120, alpha=255):
    image = Image.new("RGBA", (width, height))
    image.putdata([(x % 256, (x + y) % 256, (2 * y) % 256, alpha) for y in range(height) for x in range(width)])
    return image


class TestColorAdjustments(unittest.TestCase):
    def test_normalize_limits_and_discards(self):
        self.assertEqual(normalize({"brightness": 150, "contrast": "-30", "saturation": 0, "x": 5}),
                         {"brightness": 100, "contrast": -30})
        self.assertEqual(normalize({"brightness": "abc"}), {})
        self.assertEqual(normalize("lixo"), {})
        self.assertTrue(is_neutral({"brightness": 0}))

    def test_neutral_returns_the_same_instance(self):
        image = _gradient()
        self.assertIs(apply_tone(image, {}), image)
        self.assertIs(apply_all(image, {"brightness": 0}), image)

    def test_alpha_is_preserved(self):
        image = _gradient(alpha=77)
        for adj in ({"brightness": 40}, {"saturation": -60}, {"sharpness": 50}):
            with self.subTest(adj=adj):
                self.assertEqual(set(apply_all(image, adj).getchannel("A").getdata()), {77})

    def test_contrast_gives_the_same_pixel_on_the_whole_image_and_on_a_crop(self):
        """O pivô fixo é o que garante prévia (imagem inteira) == export (recorte)."""
        image = _gradient()
        adj = {"brightness": 20, "contrast": 45, "saturation": 30}
        whole = apply_tone(image, adj)
        crop = apply_tone(image.crop((50, 30, 150, 100)), adj)
        self.assertEqual(whole.crop((50, 30, 150, 100)).tobytes(), crop.tobytes())

    def test_brightness_and_extremes(self):
        gray = Image.new("RGB", (4, 4), (100, 100, 100))
        self.assertGreater(apply_tone(gray, {"brightness": 50}).getpixel((0, 0))[0], 100)
        self.assertEqual(apply_tone(gray, {"brightness": -100}).getpixel((0, 0)), (0, 0, 0))
        self.assertEqual(apply_tone(gray, {"saturation": -100}).getpixel((0, 0)), (100, 100, 100))

    def test_cache_token_is_stable(self):
        self.assertEqual(cache_token({"contrast": 5, "brightness": 1}), cache_token({"brightness": 1, "contrast": 5, "x": 9}))
        self.assertEqual(cache_token({}), ())


if __name__ == "__main__":
    unittest.main()
