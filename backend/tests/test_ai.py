"""Tests for the from-scratch intelligence engine (clustering, spikes, briefing, summary)."""
import time
import unittest

from app.ai.engine import (
    STOPWORDS,
    cluster_events,
    detect_spikes,
    generate_briefing,
    generate_world_summary,
    region_of,
    tokenize,
    watch_alerts,
    watch_term_stats,
)

NOW = int(time.time() * 1000)


def _event(i, title, category="news", severity=1, source="test", published=None, url=None):
    return {
        "id": f"id-{i}",
        "source": source,
        "category": category,
        "severity": severity,
        "title": title,
        "url": url,
        "summary": None,
        "published": published if published is not None else NOW - i * 60_000,
    }


class TestTokenize(unittest.TestCase):
    def test_filters_stopwords_and_short_words(self):
        toks = tokenize("The big story about a major event today")
        self.assertNotIn("the", toks)
        self.assertNotIn("big", toks)  # 3 chars → filtered
        self.assertIn("story", toks)
        self.assertIn("major", toks)

    def test_stopword_set_is_defined(self):
        self.assertIn("the", STOPWORDS)
        self.assertIn("breaking", STOPWORDS)


class TestClustering(unittest.TestCase):
    def test_similar_titles_cluster(self):
        events = [
            _event(0, "Wildfire forces evacuations near Reno Nevada"),
            _event(1, "Wildfire forces evacuations near Reno"),
            _event(2, "Local dog show winners announced today"),
        ]
        clusters = cluster_events(events)
        self.assertEqual(len(clusters), 2)

    def test_cluster_fields(self):
        clusters = cluster_events([
            _event(0, "Wildfire forces evacuations near Reno Nevada", severity=3),
            _event(1, "Wildfire forces evacuations near Reno", severity=4),
        ])
        c = clusters[0]
        self.assertEqual(c["count"], 2)
        self.assertEqual(c["severity"], 4)  # max severity in cluster
        self.assertEqual(len(c["sources"]), 1)

    def test_cluster_timeline_is_chronological(self):
        clusters = cluster_events([
            _event(0, "Wildfire near Reno", severity=3, published=NOW - 30 * 60_000),
            _event(1, "Wildfire near Reno spreading", severity=4, published=NOW - 5 * 60_000),
        ])
        tl = clusters[0]["timeline"]
        self.assertEqual(len(tl), 2)
        self.assertLessEqual(tl[0]["published"], tl[1]["published"])
        self.assertEqual(tl[0]["title"], "Wildfire near Reno")
        self.assertIn("url", tl[0])


class TestSpikes(unittest.TestCase):
    def test_no_spikes_with_few_events(self):
        self.assertEqual(detect_spikes([_event(i, f"headline {i}") for i in range(5)]), [])

    def test_detects_burst_term(self):
        events = []
        for i in range(20):
            title = f"Headline number {i} about routine business"
            if i >= 16:
                title += " aurora borealis sighting"
            events.append(_event(i, title, published=NOW - (19 - i) * 60_000))
        spikes = detect_spikes(events)
        self.assertTrue(any(s["term"] == "aurora" for s in spikes))


class TestWatchlist(unittest.TestCase):
    def test_matches_country_and_keyword(self):
        watch = {"countries": ["iran"], "keywords": ["wildfire"], "min_severity": 3}
        hits = watch_alerts([
            _event(0, "Iran nuclear talks resume", severity=4),
            _event(1, "Wildfire spreads in California", severity=2),  # below min severity
            _event(2, "Market opens higher", severity=4),
        ], watch)
        self.assertEqual(len(hits), 1)
        self.assertIn("iran", hits[0]["matched"])

    def test_respects_min_severity(self):
        watch = {"countries": [], "keywords": ["flood"], "min_severity": 3}
        hits = watch_alerts([_event(0, "Flood warning issued", severity=2)], watch)
        self.assertEqual(hits, [])


class TestWatchTermStats(unittest.TestCase):
    def test_counts_matches_per_term(self):
        watch = {"countries": ["iran"], "keywords": ["wildfire"], "min_severity": 3}
        events = [
            _event(0, "Iran nuclear talks resume", severity=4),
            _event(1, "Iran clashes reported in Tehran", severity=4),
            _event(2, "Wildfire spreads in California", severity=4),
            _event(3, "Wildfire contained", severity=2),  # below threshold
        ]
        stats = watch_term_stats(events, watch)
        by = {s["term"]: s["count"] for s in stats}
        self.assertEqual(by["iran"], 2)
        self.assertEqual(by["wildfire"], 1)
        self.assertNotIn("flood", by)

    def test_respects_min_severity(self):
        watch = {"countries": [], "keywords": ["flood"], "min_severity": 4}
        events = [_event(0, "Flood warning issued", severity=3)]
        self.assertEqual(watch_term_stats(events, watch), [])

    def test_sorted_most_active_first(self):
        watch = {"countries": ["iran"], "keywords": ["wildfire"], "min_severity": 1}
        events = [
            _event(0, "Wildfire near Reno", severity=2),
            _event(1, "Wildfire near Reno", severity=2),
            _event(2, "Wildfire near Reno", severity=2),
            _event(3, "Iran talks resume", severity=2),
        ]
        stats = watch_term_stats(events, watch)
        self.assertEqual(stats[0]["term"], "wildfire")


class TestBriefing(unittest.TestCase):
    def test_generates_headline_and_sections(self):
        events = [
            _event(0, "Massive earthquake rocks coastal city", category="disaster", severity=5, source="usgs"),
            _event(1, "Earthquake aftershocks felt across region", category="disaster", severity=4, source="gn-disaster"),
            _event(2, "Port congestion slows shipments in Rotterdam", category="supplychain", severity=3),
        ]
        b = generate_briefing(events, hours=24)
        self.assertTrue(b["headline"])
        self.assertIn("Breaking", [s["title"] for s in b["sections"]])
        self.assertIn("Natural disasters", [s["title"] for s in b["sections"]])
        self.assertIn("Supply chain & energy watch", [s["title"] for s in b["sections"]])

    def test_falls_back_when_empty(self):
        b = generate_briefing([], hours=24)
        self.assertEqual(b["headline"], "No major developments in the last 24 hours.")


class TestWorldSummary(unittest.TestCase):
    def test_regions_and_opening(self):
        events = [
            _event(0, "Fighting intensifies in eastern Ukraine", category="conflict", severity=4),
            _event(1, "Ukraine front lines under heavy shelling", category="conflict", severity=4),
            _event(2, "Taiwan chip makers boost output", category="tech", severity=2),
        ]
        s = generate_world_summary(events, hours=24)
        self.assertTrue(s["opening"].startswith("Over the last 24h"))
        region_names = {r["name"] for r in s["regions"]}
        self.assertIn("Europe", region_names)
        self.assertIn("Asia-Pacific", region_names)
        self.assertGreater(s["regions"][0]["count"], 0)

    def test_region_of(self):
        self.assertEqual(region_of("News from Iran today"), "Middle East")
        self.assertEqual(region_of("Baseball scores"), "Global")


if __name__ == "__main__":
    unittest.main()
