"""Tests for the WHO Disease Outbreak News collector (mocked feed — no network)."""
import unittest
from unittest.mock import patch

from app.collectors import who_outbreak


_FAKE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>WHO Disease Outbreak News</title>
  <item>
    <title>Outbreak of Ebola virus disease in Uganda</title>
    <link>https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON001</link>
    <description>The Ministry of Health confirmed an outbreak of Ebola virus disease.</description>
    <pubDate>Sat, 23 Aug 2026 12:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Weekly update on avian influenza A(H5N1)</title>
    <link>https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON002</link>
    <description>WHO received reports of new cases.</description>
    <pubDate>Fri, 22 Aug 2026 08:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Cholera - Sudan</title>
    <link>https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON003</link>
    <description>Continuing cholera transmission in multiple states.</description>
    <pubDate>Thu, 21 Aug 2026 10:00:00 GMT</pubDate>
  </item>
</channel>
</rss>"""


class TestGeocode(unittest.TestCase):
    def test_finds_country_in_title(self):
        geo = who_outbreak._geocode_title("Cholera - Sudan")
        self.assertIsNotNone(geo)
        self.assertAlmostEqual(geo["lat"], 12.9, places=1)
        self.assertEqual(geo["place"], "Sudan")

    def test_finds_multi_word_country(self):
        geo = who_outbreak._geocode_title("Outbreak in South Africa")
        self.assertIsNotNone(geo)
        self.assertAlmostEqual(geo["lat"], -30.6, places=1)

    def test_no_country_returns_none(self):
        geo = who_outbreak._geocode_title("Weekly update on avian influenza")
        self.assertIsNone(geo)


class TestWhoOutbreak(unittest.TestCase):
    def test_extract_entries(self):
        events = who_outbreak._extract_entries(_FAKE_RSS)
        self.assertEqual(len(events), 3)
        titles = {e["title"] for e in events}
        self.assertIn("Outbreak of Ebola virus disease in Uganda", titles)
        self.assertIn("Weekly update on avian influenza A(H5N1)", titles)

    def test_events_with_country_get_geo(self):
        events = who_outbreak._extract_entries(_FAKE_RSS)
        uganda = next(e for e in events if "uganda" in e["title"].lower())
        self.assertIsNotNone(uganda["geo"])
        self.assertIn("lat", uganda["geo"])

    def test_events_without_country_have_no_geo(self):
        events = who_outbreak._extract_entries(_FAKE_RSS)
        flu = next(e for e in events if "avian influenza" in e["title"].lower())
        self.assertIsNone(flu["geo"])

    def test_category_is_health(self):
        events = who_outbreak._extract_entries(_FAKE_RSS)
        for e in events:
            self.assertEqual(e["category"], "health")

    def test_source_is_who_don(self):
        events = who_outbreak._extract_entries(_FAKE_RSS)
        for e in events:
            self.assertEqual(e["source"], "who-don")

    def test_ebola_gets_high_severity(self):
        events = who_outbreak._extract_entries(_FAKE_RSS)
        ebola = next(e for e in events if "ebola" in e["title"].lower())
        self.assertGreaterEqual(ebola["severity"], 3)

    def test_empty_xml(self):
        events = who_outbreak._extract_entries("")
        self.assertEqual(events, [])

    def test_malformed_xml(self):
        events = who_outbreak._extract_entries("not xml at all")
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
