"""Celery app config + task registry."""
from celery import Celery
from celery.schedules import crontab

app = Celery("kisan_ai")

# Load config from settings
app.conf.update(
    broker_url="redis://localhost:6379/0",
    result_backend="redis://localhost:6379/0",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
)

# Beat schedule
app.conf.beat_schedule = {
    "ingest-weather-daily": {
        "task": "src.scheduler.tasks.ingest_weather",
        # 6:00 AM IST every day (Phase 2 Module 1)
        "schedule": crontab(hour=6, minute=0),
    },
    "broadcast-prices-daily": {
        "task": "src.scheduler.tasks.broadcast_prices",
        # 6:30 AM IST every day (runs 30 min after weather ingestion)
        "schedule": crontab(hour=6, minute=30),
    },
    "hard-delete-erased-farmers": {
        "task": "src.scheduler.tasks.hard_delete_erased_farmers",
        # 1:00 AM IST every day (= 00:30 UTC; Celery uses UTC)
        "schedule": crontab(hour=19, minute=30),  # 1:00 AM IST = 19:30 UTC previous day
    },
}

# Import tasks so they're registered
from src.scheduler import tasks  # noqa: F401, E402
