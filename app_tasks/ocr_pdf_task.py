# app_tasks/ocr_pdf_task.py
import asyncio
import json
from pathlib import Path
import redis
from app_tasks.ocr_server import ocr_pdf_to_md
from app_tasks.util import save_pdf
from celery_app import app_work
r = redis.Redis(host="localhost", port=6380, db=2, password="123456")

@app_work.task(name="app_tasks.ocr_pdf_task.pdf_to_md",
               bind=True)
def pdf_to_md(self,data: dict):
    task_id = self.request.id  
    pdf_file = data.get("file_path")
    stream_name = data.get("stream_name")
    task_type = data.get("task_type")

    result = asyncio.run(ocr_pdf_to_md(pdf_file))

    stream_name = data.get("stream_name")
    result = {
        "task_id": task_id,
        "result": result,
        "task_type":task_type,
    }
    r.xadd(stream_name, 
           {"data": json.dumps(result)},
            maxlen=1000,  # 最多保留最近 10000 条记录
            approximate=True  # 使用近似删除机制（更快）  
            )
    return result

