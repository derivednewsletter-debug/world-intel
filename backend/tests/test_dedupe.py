"""Tests for title normalization, dedupe keys, severity scoring and classification."""
import unittest

from app.dedupe import compute_severity, event_id, normalize_title, refine_category


class TestNormalizeTitle(unittest.TestCase):
    def test_lowercases_and_strips_punctuation(self):
        self.assertEqual(normalize_title("BREAKING: Wildfire! Near Reno."), "breaking wildfire near reno")

    def test_collapses_whitespace(self):
        self.assertEqual(normalize_title("a   b\tc"), "a b c")

    def test_truncates_long_titles(self):
        self.assertLessEqual(len(normalize_title("x " * 200)), 120)


class TestEventId(unittest.TestCase):
    def test_is_stable(self):
        self.assertEqual(event_id("Same Title", "https://example.com/a"), event_id("Same Title", "https://example.com/a"))

    def test_differs_by_title_or_url(self):
        self.assertNotEqual(event_id("Title A", "https://example.com/a"), event_id("Title B", "https://example.com/a"))
        self.assertNotEqual(event_id("Title", "https://example.com/a"), event_id("Title", "https://example.com/b"))

    def test_ignores_scheme_in_url(self):
        self.assertEqual(event_id("T", "http://x.com/a"), event_id("T", "https://x.com/a"))

    def test_is_hex(self):
        self.assertTrue(set(event_id("T", "u")).issubset(set("0123456789abcdef")))


class TestSeverity(unittest.TestCase):
    def test_base(self):
        self.assertEqual(compute_severity(1, "Some ordinary headline"), 1)

    def test_boosts(self):
        self.assertGreater(compute_severity(1, "Magnitude 6.4 earthquake"), compute_severity(1, "ordinary"))

    def test_clamped_to_5(self):
        self.assertEqual(compute_severity(4, "Magnitude 7 earthquake tsunami"), 5)

    def test_floored_at_0(self):
        self.assertEqual(compute_severity(-2, "quiet"), 0)


class TestRefineCategory(unittest.TestCase):
    def test_non_news_passthrough(self):
        self.assertEqual(refine_category("markets", "anything"), "markets")

    def test_retags_news_by_keywords(self):
        self.assertEqual(refine_category("news", "Missile strike hits port city"), "conflict")
        self.assertEqual(refine_category("news", "Earthquake rocks region"), "disaster")
        self.assertEqual(refine_category("news", "OPEC raises oil price"), "energy")

    def test_unknown_stays_news(self):
        self.assertEqual(refine_category("news", "Local bake sale a success"), "news")


if __name__ == "__main__":
    unittest.main()
