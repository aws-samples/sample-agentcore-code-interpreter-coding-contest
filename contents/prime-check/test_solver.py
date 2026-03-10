import unittest
from solver import solver


class TestSolver(unittest.TestCase):
    def test_one_is_not_prime(self):
        self.assertFalse(solver(1))

    def test_two_is_prime(self):
        self.assertTrue(solver(2))

    def test_three_is_prime(self):
        self.assertTrue(solver(3))

    def test_four_is_not_prime(self):
        self.assertFalse(solver(4))

    def test_small_primes(self):
        for p in [5, 7, 11, 13, 17, 19, 23, 29, 31]:
            self.assertTrue(solver(p), f"{p} should be prime")

    def test_small_composites(self):
        for c in [6, 8, 9, 10, 12, 14, 15, 16, 18, 20]:
            self.assertFalse(solver(c), f"{c} should not be prime")

    def test_large_prime(self):
        self.assertTrue(solver(104729))

    def test_large_composite(self):
        self.assertFalse(solver(104730))

    def test_square_of_prime(self):
        self.assertFalse(solver(49))  # 7*7
        self.assertFalse(solver(121))  # 11*11
