import json
import tempfile
import unittest
from pathlib import Path

from shared.zone_config import default_zones, load_defended_zones


class ZoneConfigTests(unittest.TestCase):
    def test_load_defended_zones_returns_defaults_when_missing(self):
        zones = load_defended_zones(Path("/tmp/does-not-exist-zones.json"))
        self.assertEqual([zone["type"] for zone in zones], [zone["type"] for zone in default_zones()])

    def test_load_defended_zones_reads_custom_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "zones.json"
            path.write_text(
                json.dumps(
                    {
                        "zones": [
                            {
                                "id": "ZONE-HARBOR",
                                "name": "Harbor",
                                "type": "PORT",
                                "position": {"x": 1400, "y": -900},
                                "radius_m": 650,
                                "priority": 88,
                                "health": 92,
                            }
                        ]
                    }
                )
            )
            zones = load_defended_zones(path)
        self.assertEqual(len(zones), 1)
        self.assertEqual(zones[0]["name"], "Harbor")
        self.assertEqual(zones[0]["type"], "PORT")
        self.assertEqual(zones[0]["status"], "DAMAGED")


if __name__ == "__main__":
    unittest.main()
