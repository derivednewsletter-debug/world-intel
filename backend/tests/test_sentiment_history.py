"""Tests for the sentiment history tracking feature."""
import time
import unittest

from app.ai.sentiment import sentiment_history

NOW = int(time.time() * 1000)
HOUR = 3_600_000


def _event(i, title="Story", severity=1, published=None):
    return {
        "id": f"id-{i}", "source": "test", "category": "news",
        "severity": severity, "title": title, "url": None, "summary": None,
        "published": published if published is not None else NOW - i * 60_000,
    }


class TestSentimentHistory(unittest.TestCase):
    def test_returns_correct_number_of_buckets(self):
        events = [_event(i) for i in range(5)]
        history = sentiment_history(events, hours=12)
        self.assertEqual(len(history), 12)

    def test_each_bucket_has_required_fields(self):
        events = [_event(i) for i in range(5)]
        history = sentiment_history(events, hours=6)
        for h in history:
            self.assertIn("hour", h)
            self.assertIn("score", h)
            self.assertIn("label", h)
            self.assertIn("positive", h)
            self.assertIn("negative", h)
            self.assertIn("neutral", h)
            self.assertIn("total", h)

    def test_empty_events_gives_zero_scores(self):
        history = sentiment_history([], hours=24)
        self.assertEqual(len(history), 24)
        for h in history:
            self.assertEqual(h["score"], 0.0)
            self.assertEqual(h["total"], 0)

    def test_negative_events_show_negative_sentiment(self):
        events = [
            _event(0, "Massacre kills dozens in attack", published=NOW - 30 * 60_000),
            _event(1, "War escalation bombs city", published=NOW - 45 * 60_000),
        ]
        history = sentiment_history(events, hours=1)
        # Both events are in the last hour bucket
        self.assertGreater(history[0]["negative"], 0)
        self.assertLess(history[0]["score"], 0)

    def test_positive_events_show_positive_sentiment(self):
        events = [
            _event(0, "Ceasefire peace deal reached", published=NOW - 30 * 60_000),
        ]
        history = sentiment_history(events, hours=1)
        self.assertGreater(history[0]["positive"], 0)
        self.assertGreater(history[0]["score"], 0)

    def test_events_outside_window_ignored(self):
        # Event from 5 hours ago, but only looking at 1 hour
        events = [
            _event(0, "Massacre kills dozens", published=NOW - 5 * HOUR),
        ]
        history = sentiment_history(events, hours=1)
        self.assertEqual(history[0]["total"], 0)

    def test_score_is_clamped(self):
        events = [
            _event(0, "killed dead massacre slaughter war invasion crisis crash", published=NOW - 30 * 60_000),
        ]
        history = sentiment_history(events, hours=1)
        self.assertGreaterEqual(history[0]["score"], -1.0)
        self.assertLessEqual(history[0]["score"], 1.0)


if __name__ == "__main__":
    unittest.main()
