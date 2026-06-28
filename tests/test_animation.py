import unittest

from PIL import Image

from src.config.settings import BORDA_HEIGHT, BORDA_WIDTH
from src.core.animation_processor import AnimationProcessor


class TestAnimationProcessor(unittest.TestCase):
    def setUp(self):
        self.img = Image.new("RGBA", (BORDA_WIDTH, BORDA_HEIGHT), (0, 0, 255, 255))

    def tearDown(self):
        self.img.close()

    def test_rainbow_frame_count_and_size(self):
        frames, duration = AnimationProcessor.generate_rainbow_frames(self.img, total_frames=5)
        self.assertEqual(len(frames), 5)
        self.assertGreater(duration, 0)
        for f in frames:
            self.assertEqual(f.size, (BORDA_WIDTH, BORDA_HEIGHT))
            self.assertEqual(f.mode, "RGBA")
        for f in frames:
            f.close()

    def test_rainbow_border_pixels_are_colored(self):
        """Border pixels should be non-black colored from the HSV cycle."""
        frames, _ = AnimationProcessor.generate_rainbow_frames(self.img, total_frames=3, border_width=5)
        frame = frames[0]
        pixel = frame.getpixel((0, 0))
        r, g, b, a = pixel
        self.assertEqual(a, 255)
        self.assertGreater(max(r, g, b), 200, "Border pixel should be a bright rainbow color")
        for f in frames:
            f.close()

    def test_rainbow_distinct_frames_have_different_colors(self):
        """Different frames should have different border hues."""
        frames, _ = AnimationProcessor.generate_rainbow_frames(self.img, total_frames=6, border_width=5)
        colors = set()
        for f in frames:
            r, g, b, _ = f.getpixel((0, 0))
            colors.add((r, g, b))
        self.assertGreater(len(colors), 1, "Rainbow frames should cycle through different colors")
        for f in frames:
            f.close()

    def test_neon_frame_count_and_size(self):
        frames, duration = AnimationProcessor.generate_neon_frames(self.img, "#FF00FF", total_frames=5)
        self.assertEqual(len(frames), 5)
        self.assertGreater(duration, 0)
        for f in frames:
            self.assertEqual(f.size, (BORDA_WIDTH, BORDA_HEIGHT))
            f.close()

    def test_neon_border_uses_correct_hue(self):
        """Neon frames should have the specified color channel dominant."""
        frames, _ = AnimationProcessor.generate_neon_frames(self.img, "#FF0000", total_frames=6, border_width=5)
        # First frame at sin=0.5 so r = 127 approx; red channel should be max of rgb
        pixel = frames[0].getpixel((0, 0))
        r, g, b, a = pixel
        self.assertEqual(a, 255)
        self.assertGreater(r, g, "Red should dominate for #FF0000 neon")
        self.assertGreater(r, b, "Red should dominate for #FF0000 neon")
        for f in frames:
            f.close()

    def test_strobe_frame_count(self):
        frames, duration = AnimationProcessor.generate_strobe_frames(self.img, total_frames=8)
        self.assertEqual(len(frames), 8)
        self.assertGreater(duration, 0)
        for f in frames:
            f.close()

    def test_glitch_frame_count(self):
        frames, duration = AnimationProcessor.generate_glitch_frames(self.img, total_frames=5)
        self.assertEqual(len(frames), 5)
        self.assertGreater(duration, 0)
        for f in frames:
            f.close()

    def test_spin_frame_count(self):
        frames, duration = AnimationProcessor.generate_spin_frames(self.img, "#00FF00", total_frames=6)
        self.assertEqual(len(frames), 6)
        for f in frames:
            self.assertEqual(f.size, (BORDA_WIDTH, BORDA_HEIGHT))
            f.close()

    def test_flow_frame_count(self):
        frames, duration = AnimationProcessor.generate_flow_frames(self.img, "#0000FF", total_frames=6)
        self.assertEqual(len(frames), 6)
        for f in frames:
            f.close()

    def test_overlay_only_mode_returns_transparent_center(self):
        """In overlay_only mode the center must be fully transparent."""
        border_width = 10
        frames, _ = AnimationProcessor.generate_rainbow_frames(
            self.img, total_frames=1, border_width=border_width, overlay_only=True
        )
        frame = frames[0]
        cx = BORDA_WIDTH // 2
        cy = BORDA_HEIGHT // 2
        _, _, _, alpha = frame.getpixel((cx, cy))
        self.assertEqual(alpha, 0, "Center pixel must be transparent in overlay_only mode")
        frame.close()

    def test_tuple_size_input_overlay_only(self):
        """Passing a (width, height) tuple in overlay_only mode should produce correct-size frames."""
        size = (100, 150)
        frames, _ = AnimationProcessor.generate_rainbow_frames(size, total_frames=3, overlay_only=True)
        for f in frames:
            self.assertEqual(f.size, size)
            f.close()


if __name__ == "__main__":
    unittest.main()
