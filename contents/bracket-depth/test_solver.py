import unittest

from solver import solver


class TestSolver(unittest.TestCase):
    def test_single_pair(self):
        self.assertEqual(solver("()"), 1)

    def test_nested_two(self):
        self.assertEqual(solver("(())"), 2)

    def test_nested_three(self):
        self.assertEqual(solver("((()))"), 3)

    def test_sequential(self):
        self.assertEqual(solver("()()"), 1)

    def test_sequential_and_nested(self):
        self.assertEqual(solver("()((()))"), 3)

    def test_curly(self):
        self.assertEqual(solver("{}"), 1)

    def test_curly_nested(self):
        self.assertEqual(solver("{{}}"), 2)

    def test_square(self):
        self.assertEqual(solver("[]"), 1)

    def test_square_nested(self):
        self.assertEqual(solver("[[]]"), 2)

    def test_mixed_sequential(self):
        self.assertEqual(solver("()[]{}"), 1)

    def test_mixed_nested(self):
        self.assertEqual(solver("({[]})"), 3)

    def test_deep_mixed(self):
        self.assertEqual(solver("({[()]})"), 4)

    def test_empty(self):
        self.assertEqual(solver(""), 0)

    def test_open_only(self):
        self.assertEqual(solver("("), -1)

    def test_close_only(self):
        self.assertEqual(solver(")"), -1)

    def test_unclosed(self):
        self.assertEqual(solver("(()"), -1)

    def test_extra_close(self):
        self.assertEqual(solver("())"), -1)

    def test_interleaved_invalid(self):
        self.assertEqual(solver("([)]"), -1)

    def test_interleaved_invalid_curly(self):
        self.assertEqual(solver("{[}]"), -1)


if __name__ == "__main__":
    unittest.main()
