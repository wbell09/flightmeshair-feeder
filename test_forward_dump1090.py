from __future__ import annotations

import unittest

from forward_dump1090 import convert_aircraft


class AircraftMetadataTests(unittest.TestCase):
    def test_forwards_optional_aircraft_category_and_type(self) -> None:
        observations = convert_aircraft({
            "now": 100,
            "aircraft": [{
                "hex": "abc123",
                "lat": 34.8,
                "lon": -86.9,
                "category": "a7",
                "t": "r44",
            }],
        })

        self.assertEqual(observations[0]["category"], "A7")
        self.assertEqual(observations[0]["aircraft_type"], "R44")


if __name__ == "__main__":
    unittest.main()
