
import unittest
from PIL import Image, ImageDraw
from src.core.image_processor import ImageProcessor
from src.config.settings import BORDA_WIDTH, BORDA_HEIGHT, BORDER_THICKNESS

class TestImageProcessor(unittest.TestCase):
    def setUp(self):
        # Patterned image so positional crop regressions are detectable.
        self.img = Image.new("RGBA", (800, 600), (0, 0, 0, 0))
        draw = ImageDraw.Draw(self.img)
        for x in range(0, 800, 20):
            color = (x % 256, (x * 2) % 256, (x * 3) % 256, 255)
            draw.rectangle([x, 0, min(799, x + 19), 599], fill=color)
        for y in range(0, 600, 20):
            draw.line((0, y, 799, y), fill=(255, 255, 255, 255), width=2)
        self.borda_pos = (15, 15)

    def test_resize_image(self):
        # Image is 800x600 (4:3)
        resized = ImageProcessor.resize_image(self.img, 400, 300)
        self.assertEqual(resized.size, (400, 300))
        
        # Test aspect ratio preservation
        # Request 200x200. Ratio needed: 800->200 (0.25), 600->200 (0.33). Min is 0.25.
        # Result: 800*0.25 = 200, 600*0.25 = 150.
        resized_fit = ImageProcessor.resize_image(self.img, 200, 200)
        self.assertEqual(resized_fit.size, (200, 150))

    def test_add_borda(self):
        content = Image.new("RGBA", (BORDA_WIDTH, BORDA_HEIGHT), (0, 0, 0, 0))
        final = ImageProcessor.add_borda_to_image(content, "#00FF00")
        self.assertEqual(final.size, (BORDA_WIDTH, BORDA_HEIGHT))
        self.assertEqual(final.getpixel((0, BORDA_HEIGHT // 2))[:3], (0, 255, 0))
        self.assertEqual(final.getpixel((BORDER_THICKNESS + 2, BORDA_HEIGHT // 2))[3], 0)
        
    def test_crop_logic_consistency(self):
        # Test if cropping returns consistent size
        pos = (0, 0)
        size = (800, 600)
        cropped = ImageProcessor.crop_image_to_borda(self.img, pos, size, self.borda_pos)
        self.assertEqual(cropped.size, (BORDA_WIDTH, BORDA_HEIGHT))

    def test_render_image_to_borda_matches_resized_crop_dimensions(self):
        pos = (-50, -30)
        size = (500, 375)
        resized = self.img.resize(size, Image.LANCZOS)
        cropped = ImageProcessor.crop_image_to_borda(resized, pos, size, self.borda_pos)
        rendered = ImageProcessor.render_image_to_borda(self.img, pos, size, self.borda_pos)

        self.assertEqual(rendered.size, (BORDA_WIDTH, BORDA_HEIGHT))
        self.assertEqual(list(cropped.getdata()), list(rendered.getdata()))

    def test_render_image_to_borda_matches_resized_crop_for_offset_case(self):
        pos = (102, 84)
        size = (317, 476)
        borda_pos = (170, 120)
        resized = self.img.resize(size, Image.LANCZOS)
        cropped = ImageProcessor.crop_image_to_borda(resized, pos, size, borda_pos)
        rendered = ImageProcessor.render_image_to_borda(self.img, pos, size, borda_pos)

        self.assertEqual(list(cropped.getdata()), list(rendered.getdata()))

if __name__ == "__main__":
    unittest.main()


class _FakeCascade:
    """Cascade que "detecta" um rosto fixo — evita depender do XML real."""

    def __init__(self, face=(300, 100, 120, 120)):
        self.face = face

    def detectMultiScale(self, *_args, **_kwargs):
        return [self.face] if self.face else []


class TestDefaultFit(unittest.TestCase):
    """M11: enquadramento padrão auto fit / inteligente."""

    def setUp(self):
        self.img = Image.new("RGBA", (800, 600), "white")
        self.borda_pos = (15, 15)

    def test_auto_fit_mode_matches_auto_fit(self):
        self.assertEqual(
            ImageProcessor.calculate_default_fit(self.img, self.borda_pos, "auto_fit", _FakeCascade()),
            ImageProcessor.calculate_auto_fit_pos(self.img, self.borda_pos),
        )

    def test_intelligent_mode_centers_detected_face(self):
        face = (300, 100, 120, 120)
        self.assertEqual(
            ImageProcessor.calculate_default_fit(self.img, self.borda_pos, "intelligent", _FakeCascade(face)),
            ImageProcessor.calculate_intelligent_frame_pos(self.img, face, self.borda_pos),
        )

    def test_intelligent_mode_falls_back_to_auto_fit(self):
        auto = ImageProcessor.calculate_auto_fit_pos(self.img, self.borda_pos)
        # sem cascade (XML ausente) e sem rosto detectado
        self.assertEqual(ImageProcessor.calculate_default_fit(self.img, self.borda_pos, "intelligent", None), auto)
        self.assertEqual(
            ImageProcessor.calculate_default_fit(self.img, self.borda_pos, "intelligent", _FakeCascade(face=None)),
            auto,
        )


class TestSuggestBorderColor(unittest.TestCase):
    """Cor de borda automática: matiz dominante entre os pixels vivos."""

    @staticmethod
    def _hue(hex_color):
        import colorsys
        r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
        return colorsys.rgb_to_hsv(r, g, b)[0] * 360

    def _figure(self, background, figure):
        image = Image.new("RGB", (300, 450), background)
        ImageDraw.Draw(image).ellipse((50, 80, 250, 370), fill=figure)
        return image

    def test_ignores_white_background_and_follows_the_figure(self):
        color = ImageProcessor.suggest_border_color(self._figure("white", (40, 170, 160)))
        self.assertAlmostEqual(self._hue(color), 175, delta=15)  # teal

    def test_dominant_vivid_hue_wins(self):
        image = Image.new("RGB", (300, 450), (250, 220, 120))  # amarelo ocupa quase tudo
        ImageDraw.Draw(image).rectangle((0, 0, 300, 60), fill=(60, 90, 220))
        self.assertAlmostEqual(self._hue(ImageProcessor.suggest_border_color(image)), 45, delta=15)

    def test_grayscale_image_gets_neutral_light_border(self):
        self.assertEqual(ImageProcessor.suggest_border_color(Image.new("RGB", (100, 100), (128, 128, 128))), "#d9dde4")

    def test_result_is_a_bright_visible_hex(self):
        color = ImageProcessor.suggest_border_color(self._figure((20, 20, 25), (120, 20, 30)))  # vermelho escuro
        self.assertRegex(color, r"^#[0-9a-f]{6}$")
        brightness = max(int(color[i:i + 2], 16) for i in (1, 3, 5))
        self.assertGreaterEqual(brightness, 0.74 * 255)  # clara o bastante (piso 0,75, com arredondamento)


class TestDetectFacesRanked(unittest.TestCase):
    """Rostos do maior para o menor, sem caixas repetidas do mesmo rosto."""

    def test_orders_by_area_and_drops_overlapping_duplicates(self):
        from unittest.mock import patch
        faces = [(10, 10, 40, 40), (200, 50, 120, 120), (205, 55, 110, 110), (400, 300, 80, 80)]
        with patch.object(ImageProcessor, "detect_all_anime_faces", return_value=faces):
            ranked = ImageProcessor.detect_faces_ranked(Image.new("RGB", (10, 10)), object())
        # a caixa (205,55,110,110) é o mesmo rosto que (200,50,120,120): sai
        self.assertEqual(ranked, [(200, 50, 120, 120), (400, 300, 80, 80), (10, 10, 40, 40)])

    def test_no_faces(self):
        from unittest.mock import patch
        with patch.object(ImageProcessor, "detect_all_anime_faces", return_value=[]):
            self.assertEqual(ImageProcessor.detect_faces_ranked(Image.new("RGB", (10, 10)), object()), [])
