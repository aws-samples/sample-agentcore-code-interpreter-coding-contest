import unittest

from solver import solver


class TestSolver(unittest.TestCase):
    def test_answer(self):
        self.assertEqual(solver(), "イギリス")


if __name__ == "__main__":
    unittest.main()
