"""Tests for the Slack/Discord webhook integration module."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import app.db as db
from app.push.webhooks import (
    get_config,
    save_config,
    _format_message,
    send_webhook,
)


class WebhookTestCase(unittest.TestCase):
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


class TestWebhookConfig(WebhookTestCase):
    def test_default_config(self):
        cfg = get_config()
        self.assertEqual(cfg["url"], "")
        self.assertFalse(cfg["enabled"])
        self.assertEqual(cfg["categories"], [])
        self.assertEqual(cfg["min_severity"], 4)

    def test_save_and_load(self):
        save_config(url="https://hooks.example.com/test", enabled=True,
                    categories=["conflict", "disaster"], min_severity=3)
        cfg = get_config()
        self.assertEqual(cfg["url"], "https://hooks.example.com/test")
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["categories"], ["conflict", "disaster"])
        self.assertEqual(cfg["min_severity"], 3)

    def test_partial_update(self):
        save_config(url="https://hooks.example.com/test")
        save_config(enabled=True)
        cfg = get_config()
        self.assertEqual(cfg["url"], "https://hooks.example.com/test")
        self.assertTrue(cfg["enabled"])

    def test_min_severity_clamped(self):
        save_config(min_severity=99)
        cfg = get_config()
        self.assertEqual(cfg["min_severity"], 5)
        save_config(min_severity=-1)
        cfg = get_config()
        self.assertEqual(cfg["min_severity"], 1)


class TestFormatMessage(unittest.TestCase):
    def test_basic_message(self):
        event = {"severity": 4, "category": "conflict",
                 "title": "Missile strike hits port", "source": "gdelt"}
        msg = _format_message(event)
        self.assertIn("🔴", msg)
        self.assertIn("[CONFLICT]", msg)
        self.assertIn("Missile strike hits port", msg)

    def test_with_geo(self):
        event = {"severity": 3, "category": "disaster",
                 "title": "Earthquake M6.2", "source": "usgs",
                 "geo": {"place": "Turkey"}}
        msg = _format_message(event)
        self.assertIn("📍 Turkey", msg)

    def test_with_url(self):
        event = {"severity": 5, "category": "news",
                 "title": "Breaking", "url": "https://example.com"}
        msg = _format_message(event)
        self.assertIn("https://example.com", msg)


class TestSendWebhook(WebhookTestCase):
    def test_disabled_returns_false(self):
        save_config(enabled=False, url="https://hooks.example.com/test")
        result = send_webhook({"severity": 5, "category": "news", "title": "Test"})
        self.assertFalse(result)

    def test_no_url_returns_false(self):
        save_config(enabled=True, url="")
        result = send_webhook({"severity": 5, "category": "news", "title": "Test"})
        self.assertFalse(result)

    def test_category_filter(self):
        save_config(enabled=True, url="https://hooks.example.com/test",
                    categories=["conflict"])
        # Should be filtered out
        result = send_webhook({"severity": 5, "category": "markets", "title": "Test"})
        self.assertFalse(result)

    def test_severity_filter(self):
        save_config(enabled=True, url="https://hooks.example.com/test",
                    min_severity=4)
        result = send_webhook({"severity": 2, "category": "news", "title": "Test"})
        self.assertFalse(result)

    @patch("app.push.webhooks.httpx.Client")
    def test_sends_payload(self, mock_client_cls):
        save_config(enabled=True, url="https://hooks.example.com/test")
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        event = {"severity": 5, "category": "conflict",
                 "title": "War escalation", "source": "gdelt"}
        result = send_webhook(event)
        self.assertTrue(result)
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        self.assertEqual(call_args[0][0], "https://hooks.example.com/test")
        payload = json.loads(call_args[1]["content"])
        self.assertIn("text", payload)
        self.assertIn("content", payload)


if __name__ == "__main__":
    unittest.main()
