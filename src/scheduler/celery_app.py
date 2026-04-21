"""Celery app config + task registry."""
import os
from celery import Celery
from celery.schedules import crontab

app = Celery("dhanyada")

# Read Redis URL from environment, fallback to localhost for development
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Load config from settings
app.conf.update(
    broker_url=redis_url,
    result_backend=redis_url,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    broker_connection_retry_on_startup=True,  # Fix deprecation warning
)

# Beat schedule
app.conf.beat_schedule = {
    "ingest-weather-daily": {
        "task": "src.scheduler.tasks.ingest_weather",
        # 6:00 AM IST every day (Phase 2 Module 1)
        "schedule": crontab(hour=6, minute=0),
    },
    "ingest-government-schemes-daily": {
        "task": "src.scheduler.tasks.ingest_government_schemes",
        # 6:15 AM IST every day (after weather at 6:00 AM)
        # Phase 2 Module 4
        "schedule": crontab(hour=6, minute=15),
    },
    "trigger-msp-alerts-daily": {
        "task": "src.scheduler.tasks.trigger_msp_alerts",
        # 6:20 AM IST every day (after scheme ingestion at 6:15 AM)
        # Phase 2 Module 4
        "schedule": crontab(hour=6, minute=20),
    },
    "broadcast-prices-daily": {
        "task": "src.scheduler.tasks.broadcast_prices",
        # 6:30 AM IST every day (runs 30 min after weather ingestion)
        "schedule": crontab(hour=6, minute=30),
    },
    "trigger-farm-advisories-daily": {
        "task": "src.scheduler.tasks.trigger_farm_advisories",
        # 6:45 AM IST every day (after weather ingest at 6:00, before price broadcast)
        # Phase 4 Step 3
        "schedule": crontab(hour=6, minute=45),
    },
    "ingest-prices-daily": {
        "task": "src.scheduler.tasks.ingest_prices",
        # 8:00 PM IST every day (evening price ingestion)
        # Phase 2 Module 5
        "schedule": crontab(hour=20, minute=0),
    },
    "trigger-price-alerts-daily": {
        "task": "src.scheduler.tasks.trigger_price_alerts",
        # 8:30 PM IST every day (after price ingestion at 8:00 PM)
        # Phase 2 Module 5
        "schedule": crontab(hour=20, minute=30),
    },
    "hard-delete-erased-farmers": {
        "task": "src.scheduler.tasks.hard_delete_erased_farmers",
        # 1:00 AM IST every day (= 00:30 UTC; Celery uses UTC)
        "schedule": crontab(hour=19, minute=30),  # 1:00 AM IST = 19:30 UTC previous day
    },
}

# Import tasks so they're registered
from src.scheduler import tasks  # noqa: F401, E402
