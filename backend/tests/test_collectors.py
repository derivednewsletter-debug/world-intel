"""Collector parsing tests (mocked feeds — no network)."""
import unittest
from unittest.mock import patch

from app.collectors import spaceweather


class SpaceWeatherTest(unittest.TestCase):
    def _fake_payload(self):
        return [
            {
                "issue_datetime": "2026-08-24T03:15:00Z",
                "message_type": "Warning",
                "product_id": "20260824-0315-WT",
                "message": "G3 (Strong) Geomagnetic Storm Imminent\n\nSolar wind speed ...",
            },
            {
                "issue_datetime": "2026-08-24T02:00:00Z",
                "message_type": "Alert",
                "product_id": "20260824-0200-AL",
                "message": "M-class solar flare observed",
            },
            {
                "issue_datetime": "2026-08-24T01:00:00Z",
                "message_type": "Summary",
                "product_id": "20260824-0100-SU",
                "message": "No significant activity",
            },
        ]

    def test_warning_outranks_alert_outranks_summary(self):
        seen = {}

        def fake_upsert(ev):
            seen[ev["title"]] = ev["severity"]
            return True

        with patch.object(spaceweather, "fetch_json", return_value=self._fake_payload()), \
             patch.object(spaceweather, "upsert_event", side_effect=fake_upsert):
            n = spaceweather.collect_spaceweather()
        self.assertEqual(n, 3)
        warn = next(t for t in seen if "warning" in t)
        alert = next(t for t in seen if "alert" in t)
        summary = next(t for t in seen if "summary" in t)
        self.assertGreater(seen[warn], seen[alert])
        self.assertGreater(seen[alert], seen[summary])

    def test_first_line_becomes_headline(self):
        seen = {}

        def fake_upsert(ev):
            seen[ev["title"]] = ev
            return True

        with patch.object(spaceweather, "fetch_json", return_value=self._fake_payload()), \
             patch.object(spaceweather, "upsert_event", side_effect=fake_upsert):
            spaceweather.collect_spaceweather()
        warn = next(ev for ev in seen.values() if "warning" in ev["title"])
        self.assertIn("G3 (Strong) Geomagnetic Storm Imminent", warn["title"])
        self.assertIn("G3 (Strong)", warn["summary"])
        self.assertEqual(warn["source"], "noaa-space-weather")

    def test_bad_payload_is_ignored(self):
        with patch.object(spaceweather, "fetch_json", return_value={"not": "a list"}), \
             patch.object(spaceweather, "upsert_event", return_value=True) as upsert:
            n = spaceweather.collect_spaceweather()
        self.assertEqual(n, 0)
        upsert.assert_not_called()


if __name__ == "__main__":
    unittest.main()
