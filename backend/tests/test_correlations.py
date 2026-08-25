"""Tests for the correlation engine between economic indicators and events."""
import time
import unittest

from app.ai.correlations import _pearson, _bucket_events, find_correlations

NOW = int(time.time() * 1000)
HOUR = 3_600_000


def _event(i, category="news", published=None):
    return {
        "id": f"id-{i}", "source": "test", "category": category,
        "severity": 2, "title": f"Event {i}", "url": None, "summary": None,
        "published": published if published is not None else NOW - i * 60_000,
    }


def _indicator(series_id, name, values):
    """Create an indicator with hourly history."""
    return {
        "series_id": series_id,
        "name": name,
        "category": "markets",
        "latest_value": values[-1] if values else None,
        "history": [{"date": f"2026-01-{i:02d}", "value": v} for i, v in enumerate(values, 1)],
    }


class TestPearson(unittest.TestCase):
    def test_perfect_positive(self):
        self.assertAlmostEqual(_pearson([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]), 1.0, places=3)

    def test_perfect_negative(self):
        self.assertAlmostEqual(_pearson([1, 2, 3, 4, 5], [10, 8, 6, 4, 2]), -1.0, places=3)

    def test_no_correlation(self):
        # Constant series has zero variance
        self.assertEqual(_pearson([1, 1, 1, 1], [1, 2, 3, 4]), 0.0)

    def test_too_few_points(self):
        self.assertEqual(_pearson([1, 2], [3, 4]), 0.0)

    def test_empty(self):
        self.assertEqual(_pearson([], []), 0.0)


class TestBucketEvents(unittest.TestCase):
    def test_buckets_by_category(self):
        events = [
            _event(0, category="conflict", published=NOW - 30 * 60_000),
            _event(1, category="conflict", published=NOW - 45 * 60_000),
            _event(2, category="markets", published=NOW - 10 * 60_000),
        ]
        buckets = _bucket_events(events, hours=1)
        self.assertEqual(buckets["conflict"][0], 2)
        self.assertEqual(buckets["markets"][0], 1)

    def test_empty_events(self):
        buckets = _bucket_events([], hours=6)
        self.assertEqual(buckets, {})

    def test_events_outside_window_ignored(self):
        events = [_event(0, category="news", published=NOW - 5 * HOUR)]
        buckets = _bucket_events(events, hours=1)
        self.assertEqual(buckets, {})


class TestFindCorrelations(unittest.TestCase):
    def test_returns_empty_for_no_data(self):
        self.assertEqual(find_correlations([], [], hours=24), [])

    def test_finds_positive_correlation(self):
        # Oil price and conflict events both increase together
        events = []
        for i in range(20):
            events.append(_event(i, category="conflict", published=NOW - i * 30 * 60_000))
        # Indicator that rises in sync with conflict events
        ind = _indicator("DCOILWTICO", "WTI Crude Oil", list(range(1, 25)))
        results = find_correlations(events, [ind], hours=24)
        # Should find at least one correlation
        self.assertGreater(len(results), 0)
        self.assertIn("correlation", results[0])

    def test_returns_top_15(self):
        events = []
        for i in range(50):
            events.append(_event(i, category="conflict", published=NOW - i * 30 * 60_000))
        indicators = [_indicator(f"X{i}", f"Indicator {i}", list(range(1, 25))) for i in range(20)]
        results = find_correlations(events, indicators, hours=24)
        self.assertLessEqual(len(results), 15)

    def test_result_has_required_fields(self):
        events = [_event(i, category="news", published=NOW - i * 30 * 60_000) for i in range(20)]
        ind = _indicator("VIX", "VIX", [20 + i * 0.5 for i in range(24)])
        results = find_correlations(events, [ind], hours=24)
        for r in results:
            self.assertIn("indicator", r)
            self.assertIn("category", r)
            self.assertIn("correlation", r)
            self.assertIn("direction", r)
            self.assertIn("strength", r)
            self.assertIn("description", r)

    def test_skips_indicators_with_no_data(self):
        events = [_event(i, category="news", published=NOW - i * 30 * 60_000) for i in range(20)]
        ind = _indicator("EMPTY", "Empty", [])
        results = find_correlations(events, [ind], hours=24)
        self.assertEqual(len(results), 0)


if __name__ == "__main__":
    unittest.main()
