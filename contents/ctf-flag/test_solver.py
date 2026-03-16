import unittest

from solver import solver


class TestSolver(unittest.TestCase):
    def test_flag(self):
        self.assertEqual(solver(), "FLAG{c0d3_1nt3rpr3t3r_m4st3r}")
