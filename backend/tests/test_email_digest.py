"""Tests for the email digest module."""
import os
import tempfile
import unittest

import app.db as db
from app.push.email_digest import (
    get_config,
    save_config,
    _render_html,
    _render_text,
    send_digest,
)


class EmailDigestTestCase(unittest.TestCase):
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


class TestEmailConfig(EmailDigestTestCase):
    def test_default_config(self):
        cfg = get_config()
        self.assertFalse(cfg["enabled"])
        self.assertEqual(cfg["to"], "")
        self.assertEqual(cfg["method"], "resend")

    def test_save_and_load(self):
        save_config(enabled=True, to="test@example.com", method="smtp",
                    smtp_host="smtp.gmail.com", smtp_port=587)
        cfg = get_config()
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["to"], "test@example.com")
        self.assertEqual(cfg["method"], "smtp")
        self.assertEqual(cfg["smtp_host"], "smtp.gmail.com")

    def test_partial_update(self):
        save_config(to="test@example.com")
        save_config(enabled=True)
        cfg = get_config()
        self.assertEqual(cfg["to"], "test@example.com")
        self.assertTrue(cfg["enabled"])


class TestRenderHtml(EmailDigestTestCase):
    def test_contains_headline(self):
        briefing = {"headline": "Major earthquake rocks coast", "sections": [], "generated": 123}
        html = _render_html(briefing)
        self.assertIn("Major earthquake rocks coast", html)
        self.assertIn("World Intelligence", html)

    def test_contains_sections(self):
        briefing = {
            "headline": "Test",
            "sections": [
                {"title": "Breaking", "items": [
                    {"title": "Event A", "detail": "detail A", "severity": 4, "url": "https://example.com"},
                    {"title": "Event B", "detail": "detail B", "severity": 2},
                ]},
            ],
            "generated": 123,
        }
        html = _render_html(briefing)
        self.assertIn("Breaking", html)
        self.assertIn("Event A", html)
        self.assertIn("https://example.com", html)

    def test_stress_panel(self):
        briefing = {"headline": "Test", "sections": [], "generated": 123}
        stress = {"score": 72, "level": "high"}
        html = _render_html(briefing, stress=stress)
        self.assertIn("72/100", html)
        self.assertIn("high", html)

    def test_sentiment_panel(self):
        briefing = {"headline": "Test", "sections": [], "generated": 123}
        sentiment = {"average": -0.35, "label": "negative", "total": 50}
        html = _render_html(briefing, sentiment=sentiment)
        self.assertIn("negative", html)
        self.assertIn("-0.35", html)


class TestRenderText(EmailDigestTestCase):
    def test_contains_headline(self):
        briefing = {"headline": "Breaking news today", "sections": [], "generated": 123}
        text = _render_text(briefing)
        self.assertIn("Breaking news today", text)
        self.assertIn("World Intelligence", text)

    def test_contains_sections(self):
        briefing = {
            "headline": "Test",
            "sections": [
                {"title": "Top stories", "items": [
                    {"title": "Story A", "detail": "detail A"},
                ]},
            ],
            "generated": 123,
        }
        text = _render_text(briefing)
        self.assertIn("Top stories", text)
        self.assertIn("Story A", text)


class TestSendDigest(EmailDigestTestCase):
    def test_disabled_returns_false(self):
        save_config(enabled=False, to="test@example.com")
        result = send_digest({"headline": "Test", "sections": []})
        self.assertFalse(result)

    def test_no_recipient_returns_false(self):
        save_config(enabled=True, to="")
        result = send_digest({"headline": "Test", "sections": []})
        self.assertFalse(result)

    def test_no_method_returns_false(self):
        save_config(enabled=True, to="test@example.com", method="unknown")
        result = send_digest({"headline": "Test", "sections": []})
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
