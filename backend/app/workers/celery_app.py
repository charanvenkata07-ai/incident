from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "incidentflow_workers",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone=settings.DEFAULT_TIMEZONE,
    enable_utc=True,
)
