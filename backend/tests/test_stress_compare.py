"""Tests for the historical stress comparison feature."""
import time
import unittest

from app.ai.stress import compute_stress_compare

NOW = int(time.time() * 1000)
WEEK = 7 * 24 * 3_600_000


def _event(i, title="Story", severity=1, category="news", published=None):
    return {
        "id": f"id-{i}", "source": "test", "category": category,
        "severity": severity, "title": title, "url": None, "summary": None,
        "published": published if published is not None else NOW - i * 60_000,
    }


class TestStressCompare(unittest.TestCase):
    def test_returns_current_and_last_week(self):
        events = [_event(i, severity=2) for i in range(20)]
        result = compute_stress_compare(events, hours=24)
        self.assertIn("current", result)
        self.assertIn("last_week", result)
        self.assertIn("delta", result)
        self.assertIn("trend", result)

    def test_trend_labels(self):
        self.assertIn("worse", ("worse", "better", "stable"))
        self.assertIn("better", ("worse", "better", "stable"))
        self.assertIn("stable", ("worse", "better", "stable"))

    def test_current_has_score(self):
        events = [_event(i) for i in range(5)]
        result = compute_stress_compare(events, hours=24)
        self.assertIsInstance(result["current"]["score"], int)
        self.assertGreaterEqual(result["current"]["score"], 0)
        self.assertLessEqual(result["current"]["score"], 100)

    def test_last_week_has_score(self):
        events = [_event(i) for i in range(5)]
        result = compute_stress_compare(events, hours=24)
        self.assertIsInstance(result["last_week"]["score"], int)

    def test_heavy_current_light_last_week(self):
        # This week: lots of severe events. Last week: nothing.
        events = [_event(i, severity=5, category="disaster") for i in range(30)]
        result = compute_stress_compare(events, hours=24)
        self.assertGreater(result["current"]["score"], result["last_week"]["score"])

    def test_empty_events_never_crash(self):
        result = compute_stress_compare([], hours=24)
        self.assertEqual(result["current"]["score"], 0)
        self.assertEqual(result["last_week"]["score"], 0)
        self.assertEqual(result["delta"], 0)
        self.assertEqual(result["trend"], "stable")


if __name__ == "__main__":
    unittest.main()
