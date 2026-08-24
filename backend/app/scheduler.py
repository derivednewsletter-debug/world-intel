"""Cron scheduler — APScheduler, same cadences as before."""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .collectors import (
    run_disasters, run_firms, run_fred, run_gdelt_doc, run_gdelt_points,
    run_money, run_rss, run_spaceweather, run_watch_feed, run_weather,
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
]


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
    _scheduler.start()


def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
