"""Email digest — sends daily AI briefing summaries via email.

Supports two modes:
  1. SMTP — standard email (Gmail, Outlook, any SMTP server)
  2. Resend API — simple HTTP-based email service (free tier: 100/day)

Configuration is stored in the DB kv table:
  email_enabled     — "1" to enable
  email_to          — recipient email address
  email_method      — "smtp" or "resend"
  email_smtp_host   — SMTP server hostname
  email_smtp_port   — SMTP server port (default 587)
  email_smtp_user   — SMTP username
  email_smtp_pass   — SMTP password
  email_resend_key  — Resend API key
  email_from        — sender address (default: digest@worldintel.local)
"""
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .. import db

_KV_PREFIX = "email_"


def _kv(key: str) -> str | None:
    return db.get_kv(_KV_PREFIX + key)


def _set_kv(key: str, value: str) -> None:
    db.set_kv(_KV_PREFIX + key, value)


def get_config() -> dict:
    return {
        "enabled": _kv("enabled") == "1",
        "to": _kv("to") or "",
        "method": _kv("method") or "resend",
        "smtp_host": _kv("smtp_host") or "",
        "smtp_port": int(_kv("smtp_port") or "587"),
        "smtp_user": _kv("smtp_user") or "",
        "smtp_pass": _kv("smtp_pass") or "",
        "resend_key": _kv("resend_key") or "",
        "from": _kv("from") or "digest@worldintel.local",
    }


def save_config(**kwargs) -> dict:
    for k, v in kwargs.items():
        if v is not None:
            if isinstance(v, bool):
                _set_kv(k, "1" if v else "0")
            else:
                _set_kv(k, str(v))
    return get_config()


def _render_html(briefing: dict, stress: dict = None, sentiment: dict = None) -> str:
    """Render the AI briefing as a clean HTML email."""
    headline = briefing.get("headline", "No major developments.")
    sections = briefing.get("sections", [])

    html_parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'></head>",
        "<body style='font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;",
        "background:#0b0e14;color:#e6e9f0;padding:20px;max-width:640px;margin:0 auto'>",
        "<h1 style='font-size:20px;margin:0 0 4px'>🌍 World Intelligence Daily Digest</h1>",
        f"<p style='color:#8b93a7;font-size:13px;margin:0 0 16px'>Generated {briefing.get('generated', '')}</p>",
    ]

    # Headline
    html_parts.append(
        f"<div style='background:#131824;border:1px solid #242e40;border-radius:10px;"
        f"padding:14px;margin-bottom:16px'>"
        f"<div style='color:#4f8cff;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;margin-bottom:6px'>AI Headline</div>"
        f"<div style='font-size:17px;font-weight:600'>{headline}</div></div>"
    )

    # Stress
    if stress:
        score = stress.get("score", 0)
        level = stress.get("level", "unknown")
        color = {"severe": "#ff4d4f", "high": "#ff7a45", "elevated": "#faad14", "calm": "#40c057"}.get(level, "#8b93a7")
        html_parts.append(
            f"<div style='background:#131824;border:1px solid #242e40;border-radius:10px;"
            f"padding:14px;margin-bottom:16px'>"
            f"<span style='color:#8b93a7;font-size:12px'>World Stress Index</span> "
            f"<span style='font-size:22px;font-weight:700;color:{color}'>{score}/100</span> "
            f"<span style='color:{color};text-transform:capitalize'>{level}</span></div>"
        )

    # Sentiment
    if sentiment and sentiment.get("total"):
        label = sentiment.get("label", "neutral")
        avg = sentiment.get("average", 0)
        emoji = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}.get(label, "⚪")
        html_parts.append(
            f"<div style='background:#131824;border:1px solid #242e40;border-radius:10px;"
            f"padding:14px;margin-bottom:16px'>"
            f"<span style='color:#8b93a7;font-size:12px'>Overall Sentiment</span> "
            f"<span style='font-size:15px;font-weight:600'>{emoji} {label} ({avg:+.2f})</span> "
            f"<span style='color:#8b93a7;font-size:12px'>{sentiment.get('total', 0)} events</span></div>"
        )

    # Sections
    for sec in sections:
        items = sec.get("items", [])
        if not items:
            continue
        html_parts.append(
            f"<h2 style='font-size:14px;color:#8b93a7;text-transform:uppercase;"
            f"letter-spacing:0.6px;margin:18px 0 8px'>{sec['title']}</h2>"
        )
        for it in items[:5]:
            sev = it.get("severity", 0)
            sev_color = ["#5cdbd3", "#8b93a7", "#95de64", "#ffc53d", "#ff7a45", "#ff4d4f"][min(sev, 5)]
            link = it.get("url", "")
            title = it.get("title", "")
            detail = it.get("detail", "")
            title_html = f"<a href='{link}' style='color:#e6e9f0;text-decoration:none'>{title}</a>" if link else title
            html_parts.append(
                f"<div style='border-left:3px solid {sev_color};padding:6px 10px;margin-bottom:8px;"
                f"background:#131824;border-radius:0 6px 6px 0'>"
                f"<div style='font-size:13px;font-weight:550'>{title_html}</div>"
                f"<div style='color:#8b93a7;font-size:12px'>{detail}</div></div>"
            )

    html_parts.append(
        "<div style='color:#8b93a7;font-size:11px;margin-top:24px;border-top:1px solid #242e40;padding-top:10px'>"
        "Sent by World Intelligence · personal dashboard · computed locally on your machine</div>"
    )
    html_parts.append("</body></html>")
    return "\n".join(html_parts)


def _render_text(briefing: dict, stress: dict = None, sentiment: dict = None) -> str:
    """Render a plain-text version of the briefing."""
    lines = ["🌍 World Intelligence Daily Digest", ""]

    headline = briefing.get("headline", "No major developments.")
    lines.append(f"Headline: {headline}")
    lines.append("")

    if stress:
        lines.append(f"Stress: {stress.get('score', 0)}/100 ({stress.get('level', '?')})")
    if sentiment and sentiment.get("total"):
        lines.append(f"Sentiment: {sentiment.get('label', 'neutral')} ({sentiment.get('average', 0):+.2f})")
    lines.append("")

    for sec in briefing.get("sections", []):
        lines.append(f"--- {sec['title']} ---")
        for it in sec.get("items", [])[:5]:
            lines.append(f"  • {it['title']}")
            if it.get("detail"):
                lines.append(f"    {it['detail']}")
        lines.append("")

    lines.append("Sent by World Intelligence · computed locally")
    return "\n".join(lines)


def send_digest(briefing: dict, stress: dict = None, sentiment: dict = None) -> bool:
    """Send the daily digest email. Returns True on success."""
    cfg = get_config()
    if not cfg["enabled"] or not cfg["to"]:
        return False

    subject = f"🌍 World Intelligence — {briefing.get('headline', 'Daily Digest')[:80]}"
    html_body = _render_html(briefing, stress, sentiment)
    text_body = _render_text(briefing, stress, sentiment)

    if cfg["method"] == "smtp" and cfg["smtp_host"]:
        return _send_smtp(cfg, subject, html_body, text_body)
    elif cfg["method"] == "resend" and cfg["resend_key"]:
        return _send_resend(cfg, subject, html_body, text_body)
    return False


def _send_smtp(cfg: dict, subject: str, html: str, text: str) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = cfg["from"]
        msg["To"] = cfg["to"]
        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as server:
            server.ehlo()
            if cfg["smtp_port"] == 587:
                server.starttls()
            if cfg["smtp_user"] and cfg["smtp_pass"]:
                server.login(cfg["smtp_user"], cfg["smtp_pass"])
            server.sendmail(cfg["from"], [cfg["to"]], msg.as_string())
        return True
    except Exception:  # noqa: BLE001
        return False


def _send_resend(cfg: dict, subject: str, html: str, text: str) -> bool:
    try:
        import httpx
        with httpx.Client(timeout=15.0) as client:
            res = client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {cfg['resend_key']}"},
                json={
                    "from": cfg["from"],
                    "to": [cfg["to"]],
                    "subject": subject,
                    "html": html,
                    "text": text,
                },
            )
            return res.status_code in (200, 201)
    except Exception:  # noqa: BLE001
        return False
