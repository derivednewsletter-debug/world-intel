"""Tests for the effective watchlist (DB override over config defaults)."""
import os
import tempfile
import unittest

import app.db as db
import app.watchlist as wl


class WatchlistTestCase(unittest.TestCase):
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


class TestEffectiveWatchlist(WatchlistTestCase):
    def test_defaults_when_no_override(self):
        w = wl.effective_watchlist()
        self.assertIn("iran", w["countries"])
        self.assertIn("wildfire", w["keywords"])

    def test_override_wins_after_save(self):
        wl.save_watchlist(["japan", "India"], ["tsunami", "Chip Shortage"], 4)
        w = wl.effective_watchlist()
        self.assertEqual(w["countries"], ["japan", "india"])  # normalized
        self.assertEqual(w["keywords"], ["tsunami", "chip shortage"])
        self.assertEqual(w["min_severity"], 4)

    def test_save_cleans_and_dedupes(self):
        wl.save_watchlist(["  Iran ", "iran", "Japan"], ["oil"], None)
        w = wl.effective_watchlist()
        self.assertEqual(w["countries"], ["iran", "japan"])

    def test_clamps_min_severity(self):
        wl.save_watchlist(["x"], ["y"], 99)
        self.assertEqual(wl.effective_watchlist()["min_severity"], 5)

    def test_reset_restores_defaults(self):
        from app.config import WATCHLIST_DEFAULTS
        wl.save_watchlist(["x"], ["y"], 4)
        wl.reset_watchlist()
        self.assertEqual(wl.effective_watchlist(), WATCHLIST_DEFAULTS)


class TestKv(WatchlistTestCase):
    def test_roundtrip(self):
        self.assertIsNone(db.get_kv("anything"))
        db.set_kv("anything", "hello")
        self.assertEqual(db.get_kv("anything"), "hello")
        db.set_kv("anything", "bye")
        self.assertEqual(db.get_kv("anything"), "bye")


if __name__ == "__main__":
    unittest.main()
