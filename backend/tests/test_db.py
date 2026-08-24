"""Tests for the SQLite data layer — run against a throwaway temp database."""
import os
import tempfile
import time
import unittest

import app.db as db

NOW = int(time.time() * 1000)


def _event(i, title, category="news", severity=2, source="test", published=None):
    return {
        "id": f"ev-{i}",
        "source": source,
        "category": category,
        "severity": severity,
        "title": title,
        "url": f"https://example.com/{i}",
        "summary": None,
        "published": published if published is not None else NOW - i * 60_000,
    }


class DbTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db.DB_PATH = self.path
        db.init_db()

    def tearDown(self):
        try:
            os.remove(self.path)
        except OSError:
            pass


class TestEvents(DbTestCase):
    def test_insert_and_query(self):
        self.assertTrue(db.upsert_event(_event(1, "First story")))
        events = db.get_events(limit=10)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "First story")
        self.assertEqual(events[0]["source"], "test")

    def test_dedupes_same_normalized_title_within_24h(self):
        self.assertTrue(db.upsert_event(_event(1, "Wildfire: Evacuations Ordered!")))
        self.assertFalse(db.upsert_event(_event(2, "Wildfire evacuations ordered")))
        self.assertEqual(db.count_events(), 1)

    def test_allows_same_title_after_24h(self):
        old = NOW - 25 * 3_600_000
        self.assertTrue(db.upsert_event(_event(1, "Old story", published=old)))
        self.assertTrue(db.upsert_event(_event(2, "Old story", published=NOW)))
        self.assertEqual(db.count_events(), 2)

    def test_category_and_severity_filters(self):
        db.upsert_event(_event(1, "Conflict news", category="conflict", severity=4))
        db.upsert_event(_event(2, "Market news", category="markets", severity=2))
        self.assertEqual(len(db.get_events(category="conflict")), 1)
        self.assertEqual(len(db.get_events(min_severity=3)), 1)
        self.assertEqual(len(db.get_events(category="conflict", min_severity=3)), 1)
        self.assertEqual(len(db.get_events(category="conflict", min_severity=5)), 0)

    def test_search(self):
        db.upsert_event(_event(1, "Port congestion in Rotterdam"))
        db.upsert_event(_event(2, "Football scores"))
        self.assertEqual(len(db.get_events(q="rotterdam")), 1)
        self.assertEqual(len(db.get_events(q="football")), 1)
        self.assertEqual(len(db.get_events(q="nonexistent")), 0)

    def test_get_event_by_id(self):
        db.upsert_event(_event(1, "A specific story"))
        ev = db.get_event("ev-1")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["title"], "A specific story")
        self.assertIsNone(db.get_event("does-not-exist"))

    def test_geo_roundtrip(self):
        ev = _event(1, "Located event")
        ev["geo"] = {"lat": 12.5, "lon": -45.2, "place": "Somewhere"}
        db.upsert_event(ev)
        got = db.get_events(with_geo=True)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["geo"]["lat"], 12.5)
        self.assertEqual(got[0]["geo"]["lon"], -45.2)

    def test_prune(self):
        db.upsert_event(_event(1, "Fresh", published=NOW))
        db.upsert_event(_event(2, "Stale", published=NOW - 10 * 86_400_000))
        removed = db.prune_events(7 * 86_400_000)
        self.assertEqual(removed, 1)
        self.assertEqual(db.count_events(), 1)


class TestIndicators(DbTestCase):
    def test_roundtrip(self):
        db.set_indicator({
            "series_id": "CPIAUCSL", "name": "US CPI", "category": "markets", "unit": "index",
            "latest_value": 332.8, "latest_date": "2026-07-01",
            "history": [{"date": "2026-06-01", "value": 331.9}],
        })
        inds = db.get_indicators()
        self.assertEqual(len(inds), 1)
        self.assertEqual(inds[0]["latest_value"], 332.8)
        self.assertEqual(len(inds[0]["history"]), 1)

    def test_overwrite(self):
        db.set_indicator({"series_id": "X", "name": "A", "category": "markets", "latest_value": 1.0})
        db.set_indicator({"series_id": "X", "name": "A", "category": "markets", "latest_value": 2.0})
        self.assertEqual(len(db.get_indicators()), 1)
        self.assertEqual(db.get_indicators()[0]["latest_value"], 2.0)


class TestSourceStatus(DbTestCase):
    def test_roundtrip_and_cooldown(self):
        db.set_source_status("src-a", True, count=12)
        st = db.get_source_status()
        self.assertEqual(len(st), 1)
        self.assertEqual(st[0]["last_ok"], 1)
        self.assertEqual(st[0]["count"], 12)
        self.assertFalse(db.is_in_cooldown("src-a"))
        db.set_cooldown("src-a", 30)
        self.assertTrue(db.is_in_cooldown("src-a"))


class TestBatchUpsert(DbTestCase):
    def test_batch_inserts_many(self):
        events = [_event(i, f"Batch story {i}") for i in range(20)]
        n, inserted = db.upsert_events_batch(events)
        self.assertEqual(n, 20)
        self.assertEqual(len(inserted), 20)
        self.assertEqual(db.count_events(), 20)

    def test_batch_dedupes(self):
        events = [
            _event(1, "Same headline"),
            _event(2, "Same headline"),
            _event(3, "Different story"),
        ]
        n, inserted = db.upsert_events_batch(events)
        self.assertEqual(n, 2)  # one deduped
        self.assertEqual(len(inserted), 2)
        self.assertEqual(db.count_events(), 2)

    def test_batch_empty_list(self):
        n, inserted = db.upsert_events_batch([])
        self.assertEqual(n, 0)
        self.assertEqual(inserted, [])


class TestGetIndicator(DbTestCase):
    def test_direct_lookup(self):
        db.set_indicator({"series_id": "VIX", "name": "VIX", "category": "markets",
                          "latest_value": 25.0, "latest_date": "2026-08-01",
                          "history": [{"date": "2026-07-01", "value": 22.0}]})
        ind = db.get_indicator("VIX")
        self.assertIsNotNone(ind)
        self.assertEqual(ind["latest_value"], 25.0)
        self.assertEqual(len(ind["history"]), 1)

    def test_missing_returns_none(self):
        self.assertIsNone(db.get_indicator("NONEXISTENT"))


class TestCountByCategory(DbTestCase):
    def test_groups_correctly(self):
        db.upsert_event(_event(1, "Conflict A", category="conflict"))
        db.upsert_event(_event(2, "Conflict B", category="conflict"))
        db.upsert_event(_event(3, "Market A", category="markets"))
        counts = db.count_events_by_category()
        self.assertEqual(counts["conflict"], 2)
        self.assertEqual(counts["markets"], 1)
        self.assertNotIn("disaster", counts)

    def test_empty_db(self):
        counts = db.count_events_by_category()
        self.assertEqual(counts, {})


class TestActivityBuckets(DbTestCase):
    def test_buckets_across_hours(self):
        # Use a fixed anchor 3h in the past so all events land cleanly.
        anchor = int(time.time() * 1000) - 3 * 3_600_000
        db.upsert_event(_event(1, "2h ago", published=anchor + 0))
        db.upsert_event(_event(2, "1h ago", published=anchor + 3_600_000))
        db.upsert_event(_event(3, "Now", published=anchor + 2 * 3_600_000))
        buckets = db.get_activity_buckets(anchor, 3)
        self.assertEqual(len(buckets), 3)
        self.assertEqual(buckets[0]["count"], 1)  # oldest hour
        self.assertEqual(buckets[1]["count"], 1)
        self.assertEqual(buckets[2]["count"], 1)  # newest hour

    def test_empty_buckets(self):
        now = int(time.time() * 1000)
        buckets = db.get_activity_buckets(now - 24 * 3_600_000, 24)
        self.assertEqual(len(buckets), 24)
        self.assertTrue(all(b["count"] == 0 for b in buckets))


class TestRelatedEvents(DbTestCase):
    def test_finds_same_norm_title(self):
        db.upsert_event(_event(1, "Wildfire forces evacuations near Reno"))
        db.upsert_event(_event(2, "Wildfire forces evacuations near Reno spread"))
        db.upsert_event(_event(3, "Completely unrelated story"))
        related = db.get_related_events("ev-1")
        # Should find at least the prefix-matched events
        ids = {e["id"] for e in related}
        self.assertIn("ev-1", ids)

    def test_nonexistent_event_returns_empty(self):
        self.assertEqual(db.get_related_events("does-not-exist"), [])


class TestGetEventsBatch(DbTestCase):
    def test_many_inserts_then_query(self):
        events = [_event(i, f"Story {i}") for i in range(100)]
        db.upsert_events_batch(events)
        results = db.get_events(limit=50)
        self.assertEqual(len(results), 50)
        self.assertEqual(db.count_events(), 100)


if __name__ == "__main__":
    unittest.main()
