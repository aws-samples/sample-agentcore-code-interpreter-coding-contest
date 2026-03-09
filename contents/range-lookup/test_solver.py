import unittest

from solver import solver


class TestSolver(unittest.TestCase):
    def test_free_zero(self):
        self.assertEqual(solver(0), "Free")

    def test_free_mid(self):
        self.assertEqual(solver(500000), "Free")

    def test_free_boundary(self):
        self.assertEqual(solver(1000000), "Free")

    def test_pro_start(self):
        self.assertEqual(solver(1000001), "Pro")

    def test_pro_mid(self):
        self.assertEqual(solver(5000000), "Pro")

    def test_pro_boundary(self):
        self.assertEqual(solver(10000000), "Pro")

    def test_business_start(self):
        self.assertEqual(solver(10000001), "Business")

    def test_business_mid(self):
        self.assertEqual(solver(50000000), "Business")

    def test_business_boundary(self):
        self.assertEqual(solver(125000000), "Business")

    def test_premium_start(self):
        self.assertEqual(solver(125000001), "Premium")

    def test_premium_mid(self):
        self.assertEqual(solver(300000000), "Premium")

    def test_premium_boundary(self):
        self.assertEqual(solver(500000000), "Premium")

    def test_enterprise_start(self):
        self.assertEqual(solver(500000001), "担当SAにご相談ください")

    def test_enterprise_large(self):
        self.assertEqual(solver(1000000000), "担当SAにご相談ください")


if __name__ == "__main__":
    unittest.main()
