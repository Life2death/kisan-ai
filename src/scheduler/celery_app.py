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
    "broadcast-prices-daily": {
        "task": "src.scheduler.tasks.broadcast_prices",
        # 6:30 AM IST every day
        "schedule": crontab(hour=6, minute=30),
    },
}

# Import tasks so they're registered
from src.scheduler import tasks  # noqa: F401, E402
