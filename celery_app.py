# celery_app.py
#celery -A celery_app.app_work worker -l info -Q task_celery_queue_ocet_work -n ocr_worker1@%h --concurrency=1 --pool=solo
from celery import Celery
from logger_conf import logger


app_work = Celery(
    "tasks",
    broker="redis://:123456@localhost:6380/0",
    backend="redis://:123456@localhost:6380/1",
    include=["app_tasks.ocr_pdf_task"],
    task_routes={
        "app_tasks.ocr_pdf_task.pdf_to_md": {"queue": "task_celery_queue_ocet_work"},
    },
    task_track_started = True,
)


app_work.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True, 
    task_default_queue="task_celery_queue_work"
)
logger.info("celery启动成功")