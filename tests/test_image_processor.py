
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
