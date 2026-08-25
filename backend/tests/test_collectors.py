"""Collector parsing tests (mocked feeds — no network)."""
import unittest
from unittest.mock import patch

try:
    from app.collectors import spaceweather
except ImportError:
    spaceweather = None  # feedparser not installed — skip these tests


def _make_fake_batch():
    """Return a side-effect function for upsert_events_batch.

    Mimics the real signature: takes a list of events, returns
    ``(count, inserted_list)`` — matching db.upsert_events_batch.
    """
    seen = {}

    def _side_effect(events):
        for ev in events:
            seen[ev["title"]] = ev
        return len(events), events

    return seen, _side_effect


@unittest.skipUnless(spaceweather, "feedparser not installed")
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
        seen, side_effect = _make_fake_batch()
        with patch.object(spaceweather, "fetch_json", return_value=self._fake_payload()), \
             patch.object(spaceweather, "upsert_events_batch", side_effect=side_effect), \
             patch.object(spaceweather, "hub"):
            n = spaceweather.collect_spaceweather()
        self.assertEqual(n, 3)
        warn = next(t for t in seen if "warning" in t)
        alert = next(t for t in seen if "alert" in t)
        summary = next(t for t in seen if "summary" in t)
        self.assertGreater(seen[warn]["severity"], seen[alert]["severity"])
        self.assertGreater(seen[alert]["severity"], seen[summary]["severity"])

    def test_first_line_becomes_headline(self):
        seen, side_effect = _make_fake_batch()
        with patch.object(spaceweather, "fetch_json", return_value=self._fake_payload()), \
             patch.object(spaceweather, "upsert_events_batch", side_effect=side_effect), \
             patch.object(spaceweather, "hub"):
            spaceweather.collect_spaceweather()
        warn = next(ev for ev in seen.values() if "warning" in ev["title"])
        self.assertIn("G3 (Strong) Geomagnetic Storm Imminent", warn["title"])
        self.assertIn("G3 (Strong)", warn["summary"])
        self.assertEqual(warn["source"], "noaa-space-weather")

    def test_bad_payload_is_ignored(self):
        with patch.object(spaceweather, "fetch_json", return_value={"not": "a list"}), \
             patch.object(spaceweather, "upsert_events_batch") as batch_mock, \
             patch.object(spaceweather, "hub"):
            n = spaceweather.collect_spaceweather()
        self.assertEqual(n, 0)
        batch_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
