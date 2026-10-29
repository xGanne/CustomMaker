import unittest

from src.core.history import Snapshot


class TestSnapshot(unittest.TestCase):
    def test_shifted_moves_only_the_position(self):
        snapshot = Snapshot(None, (10, 20), (100, 200), False, label="Mover", timestamp=5.0)
        moved = snapshot.shifted(3, -4)
        self.assertEqual(moved.pos, (13, 16))
        self.assertEqual((moved.size, moved.pixel_edited, moved.label, moved.timestamp), ((100, 200), False, "Mover", 5.0))
        self.assertEqual(snapshot.pos, (10, 20))


if __name__ == "__main__":
    unittest.main()
