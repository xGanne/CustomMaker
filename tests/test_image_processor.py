
import unittest
from PIL import Image
from src.core.image_processor import ImageProcessor
from src.config.settings import BORDA_WIDTH, BORDA_HEIGHT

class TestImageProcessor(unittest.TestCase):
    def setUp(self):
        # Create a dummy image for testing
        self.img = Image.new("RGBA", (800, 600), "blue")
        self.borda_pos = (15, 15, 240, 365) # Example border pos

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
        # Test if adding border returns an image of correct size (indirectly)
        # Actually add_borda_to_image implementation might assume input is exactly BORDA_WIDTH x BORDA_HEIGHT
        # or it might resize. Let's check implementation behavior
        
        # Based on code: add_borda_to_image(image_content, hex_color)
        # It creates a new image of BORDA_WIDTH x BORDA_HEIGHT and composites
        
        content = Image.new("RGBA", (BORDA_WIDTH, BORDA_HEIGHT), "red")
        final = ImageProcessor.add_borda_to_image(content, "#00FF00")
        
        self.assertEqual(final.size, (BORDA_WIDTH, BORDA_HEIGHT))
        
    def test_crop_logic_consistency(self):
        # Test if cropping returns consistent size
        pos = (0, 0)
        size = (800, 600)
        # crop_image_to_borda(image, pos, size, borda_pos)
        # It crops relative to canvas logic.
        # This is UI dependent logic usually, but let's see if we can test basic bounds
        pass

if __name__ == "__main__":
    unittest.main()
