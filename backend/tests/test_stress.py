"""Tests for the World Stress Index composite score."""
import time
import unittest

from app.ai.stress import compute_stress

NOW = int(time.time() * 1000)


def _event(i, title="Story", severity=1, category="news", published=None):
    return {
        "id": f"id-{i}", "source": "test", "category": category, "severity": severity,
        "title": title, "url": None, "summary": None,
        "published": published if published is not None else NOW - i * 60_000,
    }


class TestStress(unittest.TestCase):
    def test_calm_with_quiet_day(self):
        events = [_event(i) for i in range(5)]
        s = compute_stress(events, hours=24)
        self.assertLess(s["score"], 30)
        self.assertEqual(s["level"], "calm")
        self.assertEqual(len(s["history"]), 24)

    def test_severe_with_heavy_activity(self):
        events = []
        for i in range(60):
            events.append(_event(i, "Major earthquake tsunami", severity=5, category="disaster"))
        s = compute_stress(events, hours=24)
        self.assertGreater(s["score"], 60)

    def test_components_and_history_shape(self):
        events = [_event(i, "Breaking event", severity=4) for i in range(6)]
        s = compute_stress(events, indicators=[], watch_count=4, hours=12)
        for key in ("pressure", "breaking", "disasters", "volatility", "watchlist"):
            self.assertIn(key, s["components"])
        self.assertTrue(all(0 <= c <= 100 for c in s["components"].values()))
        self.assertEqual(len(s["history"]), 12)
        self.assertEqual(s["history"][0]["hour"] + 3_600_000, s["history"][1]["hour"])

    def test_vix_drives_volatility_component(self):
        indicators = [{"series_id": "VIXCLS", "latest_value": 35.0}]
        s = compute_stress([], indicators=indicators, hours=24)
        self.assertGreater(s["components"]["volatility"], 50)

    def test_empty_events_never_crash(self):
        s = compute_stress([], hours=24)
        self.assertGreaterEqual(s["score"], 0)
        self.assertLessEqual(s["score"], 100)


if __name__ == "__main__":
    unittest.main()
