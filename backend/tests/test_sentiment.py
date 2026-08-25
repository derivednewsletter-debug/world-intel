"""Tests for the keyword-based sentiment analysis module."""
import unittest

from app.ai.sentiment import (
    cluster_sentiment,
    score_events,
    score_text,
    timeline_sentiment,
)


class TestScoreText(unittest.TestCase):
    def test_negative_headline(self):
        s = score_text("Massive earthquake kills dozens in Turkey")
        self.assertLess(s["score"], -0.05)
        self.assertEqual(s["label"], "negative")
        self.assertGreater(s["negative"], 0)

    def test_positive_headline(self):
        s = score_text("Ceasefire deal reached after months of peace negotiations")
        self.assertGreater(s["score"], 0.05)
        self.assertEqual(s["label"], "positive")
        self.assertGreater(s["positive"], 0)

    def test_neutral_headline(self):
        s = score_text("Weather forecast for Monday expected conditions")
        self.assertEqual(s["label"], "neutral")
        self.assertAlmostEqual(s["score"], 0.0, places=1)

    def test_empty_text(self):
        s = score_text("")
        self.assertEqual(s["score"], 0.0)
        self.assertEqual(s["label"], "neutral")

    def test_none_text(self):
        s = score_text(None)
        self.assertEqual(s["score"], 0.0)

    def test_score_clamped(self):
        # Very negative text shouldn't go below -1.0
        s = score_text("killed dead massacre slaughter war invasion crisis crash")
        self.assertGreaterEqual(s["score"], -1.0)
        self.assertLessEqual(s["score"], 1.0)


class TestScoreEvents(unittest.TestCase):
    def test_mixed_events(self):
        events = [
            {"title": "War escalation kills many", "summary": None},
            {"title": "Peace deal signed", "summary": None},
        ]
        result = score_events(events)
        self.assertEqual(result["total"], 2)
        self.assertIn(result["label"], ("negative", "positive", "neutral"))

    def test_empty_events(self):
        result = score_events([])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["label"], "neutral")

    def test_all_negative(self):
        events = [
            {"title": "Massacre reported", "summary": None},
            {"title": "Hundreds killed in bombing", "summary": None},
        ]
        result = score_events(events)
        self.assertGreater(result["negative_count"], 0)
        self.assertLess(result["average"], 0)


class TestClusterSentiment(unittest.TestCase):
    def test_adds_sentiment_to_cluster(self):
        cluster = {
            "sample": [
                {"title": "Ceasefire holds in region", "summary": None},
                {"title": "Peace talks resume", "summary": None},
            ]
        }
        result = cluster_sentiment(cluster)
        self.assertIn("sentiment", result)
        self.assertIn("score", result["sentiment"])
        self.assertIn("label", result["sentiment"])


class TestTimelineSentiment(unittest.TestCase):
    def test_scores_each_entry(self):
        timeline = [
            {"published": 1000, "title": "Disaster strikes", "source": "test"},
            {"published": 2000, "title": "Recovery efforts underway", "source": "test"},
        ]
        result = timeline_sentiment(timeline)
        self.assertEqual(len(result), 2)
        self.assertIn("sentiment", result[0])
        self.assertIn("sentiment", result[1])


if __name__ == "__main__":
    unittest.main()
