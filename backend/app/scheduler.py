"""Cron scheduler — APScheduler, same cadences as before."""
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .collectors import (
    run_disasters, run_firms, run_fred, run_gdelt_doc, run_gdelt_points,
    run_money, run_rss, run_spaceweather, run_watch_feed, run_weather,
    run_who_outbreak,
)
from .config import RETENTION_DAYS, SCHEDULE
from .db import prune_events

_scheduler = BackgroundScheduler(timezone="UTC")

_JOBS = [
    ("rss", SCHEDULE["rss"], run_rss),
    ("gdelt_doc", SCHEDULE["gdelt_doc"], run_gdelt_doc),
    ("gdelt_points", SCHEDULE["gdelt_points"], run_gdelt_points),
    ("disasters", SCHEDULE["disasters"], run_disasters),
    ("firms", SCHEDULE["firms"], run_firms),
    ("fred", SCHEDULE["fred"], run_fred),
    ("weather", SCHEDULE["weather"], run_weather),
    ("spaceweather", SCHEDULE["spaceweather"], run_spaceweather),
    ("watch", SCHEDULE["watch"], run_watch_feed),
    ("money", SCHEDULE["money"], run_money),
    ("who_outbreak", "*/15 * * * *", run_who_outbreak),
]


def _run_daily_digest() -> None:
    """Generate and send the daily digest email."""
    try:
        from .push.email_digest import get_config, send_digest
        cfg = get_config()
        if not cfg["enabled"] or not cfg["to"]:
            return
        from .ai.engine import generate_briefing, watch_alerts
        from .ai.sentiment import score_events
        from .ai.stress import compute_stress
        from . import db, watchlist
        hours = 24
        events = db.get_all_events_since(int(time.time() * 1000) - hours * 3_600_000)
        briefing = generate_briefing(events, hours)
        wl = watchlist.effective_watchlist()
        watch_count = len(watch_alerts(events, wl))
        stress = compute_stress(events, db.get_indicators(), watch_count=watch_count, hours=hours)
        sentiment = score_events(events)
        send_digest(briefing, stress, sentiment)
    except Exception:  # noqa: BLE001
        pass  # digest failure must never crash the scheduler


def start_scheduler() -> None:
    if _scheduler.running:
        return  # already running — never double-register jobs or re-start
    for job_id, cron, fn in _JOBS:
        _scheduler.add_job(
            fn, CronTrigger.from_crontab(cron), id=job_id,
            max_instances=1, coalesce=True, misfire_grace_time=300,
        )
    # Nightly retention prune
    _scheduler.add_job(
        lambda: prune_events(RETENTION_DAYS * 86_400_000),
        CronTrigger.from_crontab("0 4 * * *"),
        id="prune",
    )
    # Daily digest — runs at 7:00 UTC (configurable via email_digest_time kv)
    _scheduler.add_job(
        _run_daily_digest,
        CronTrigger.from_crontab("0 7 * * *"),
        id="daily_digest",
        max_instances=1, coalesce=True, misfire_grace_time=600,
    )
    _scheduler.start()


def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
