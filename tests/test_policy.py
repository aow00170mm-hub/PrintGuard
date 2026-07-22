import unittest
from server import evaluate

class PolicyTests(unittest.TestCase):
    def test_mono_converts_color(self): self.assertEqual(evaluate("mono", 1, True)[:2], (True, False))
    def test_color_converts_mono(self): self.assertEqual(evaluate("color", 1, False)[:2], (True, True))
    def test_incapable_blocks_color(self): self.assertEqual(evaluate("any", 0, True)[0], False)
    def test_any_allows_mono(self): self.assertEqual(evaluate("any", 1, False)[:2], (True, False))

if __name__ == "__main__": unittest.main()
