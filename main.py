from fastapi import BackgroundTasks, Body, FastAPI, File, UploadFile, WebSocket
from websocket.websocket_handler import WebSocketHandler
import shutil
import uuid
from pathlib import Path
from logger_conf import logger
from celery_app import app_work

app = FastAPI()

def save_file(file_byte: bytes, 
            file_path: Path,
            file_id: str,
            user_id: str,
            task_type:str):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "wb") as buffer:
        buffer.write(file_byte)    
    data = {
        "stream_name": f"stream:task:{user_id}",
        "file_path": str(file_path),
        "task_type": task_type,
    }
    app_work.send_task("app_tasks.ocr_pdf_task.pdf_to_md", args=[data], task_id=file_id)
    


@app.websocket("/ws/{user_id}")
async def ws(user_id: str, websocket: WebSocket):
    handler = WebSocketHandler(websocket,user_id)
    await handler.start()

@app.post("/upload")
async def upload_file(background_tasks: BackgroundTasks,
                      user_id: str = Body(..., description="用户ID"),#注意和ws的user_id保持一致
                    file_id:str = Body(..., description="文件ID"),
                    file:UploadFile = File(description="PDF文件"),
                    task_type:str = Body(..., description="任务类型")):
    file_path = Path("tmp")/f'{str(uuid.uuid4())[:5]}-{file.filename}'
    file_byte = await file.read()    
    logger.info(f"收到OCR {file.filename}请求;task_id:{file_id}")
    background_tasks.add_task(save_file, 
                              file_path=file_path, 
                              file_byte=file_byte, 
                              file_id  = file_id,
                              user_id = user_id,
                              task_type = task_type)
    return {"file_id": file_id, "file_path": str(file.filename),"task_type":task_type}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3007)