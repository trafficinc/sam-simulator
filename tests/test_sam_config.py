import unittest

from shared.sam_config import load_sam_batteries


class SamConfigTests(unittest.TestCase):
    def test_default_sam_battery_config_loads(self):
        batteries = load_sam_batteries()
        self.assertGreaterEqual(len(batteries), 1)
        self.assertEqual(batteries[0]["id"], "BTRY-A")
        self.assertEqual(batteries[0]["ammo"], 8)
        self.assertEqual(batteries[0]["max_channels"], 2)


if __name__ == "__main__":
    unittest.main()
