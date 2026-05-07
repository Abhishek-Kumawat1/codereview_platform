"""
Celery application instance.
This file is imported by the Celery worker process.
"""
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

app = Celery('codereview')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """
    A simple task for verifying Celery is working.
    """
    print(f'Request: {self.request!r}')