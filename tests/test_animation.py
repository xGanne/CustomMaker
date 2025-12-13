
import unittest
from PIL import Image
from src.core.animation_processor import AnimationProcessor
from src.config.settings import BORDA_WIDTH, BORDA_HEIGHT

class TestAnimationProcessor(unittest.TestCase):
    def setUp(self):
        self.img = Image.new("RGBA", (BORDA_WIDTH, BORDA_HEIGHT), "blue")

    def test_basic_frame_generation(self):
        # Test if generator returns frames
        frames, duration = AnimationProcessor.generate_rainbow_frames(self.img, total_frames=5)
        self.assertTrue(len(frames) == 5)
        self.assertTrue(duration > 0)
        
        # Check size of generated frames (Processor itself might return different sizes based on implementation,
        # but the BatchController is responsible for enforcing final output.
        # However, let's see what AnimationProcessor returns.)
        for f in frames:
            # The current implementation of AnimationProcessor creates a new image of size img.size
            # So it should match input size
            self.assertEqual(f.size, (BORDA_WIDTH, BORDA_HEIGHT))

    def test_neon_frames(self):
        frames, duration = AnimationProcessor.generate_neon_frames(self.img, "#FF00FF", total_frames=5)
        self.assertTrue(len(frames) == 5)
        for f in frames:
            self.assertEqual(f.size, (BORDA_WIDTH, BORDA_HEIGHT))

if __name__ == "__main__":
    unittest.main()
