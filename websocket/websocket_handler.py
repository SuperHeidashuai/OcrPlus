import asyncio
import json
import redis.asyncio as aioredis
from fastapi import  WebSocket
from celery_app import app_work
from logger_conf import logger

class WebSocketHandler:
    def __init__(self, ws: WebSocket,user_id: str):
        self.ws = ws
        self.user_id = user_id  
        self.stream_name = f"stream:task:{user_id}"        
        self.redis = aioredis.Redis(
            host="localhost", port=6380, db=2, password="123456"
        )
        self.consumer_task = None
        self.active = True
        self.last_id = "0"
        self.is_closed = False 

    async def start(self):
        await self.ws.accept()
        logger.info(f"✅ 用户 {self.user_id} WebSocket 已连接")

        last_id = await self.redis.hget("stream:last_id", self.user_id)
        if last_id:
            self.last_id = last_id.decode()

        self.consumer_task = asyncio.create_task(self.consume_stream())

        try:
            await self.listen_user_input()
        finally:
            await self.cleanup()

    async def consume_stream(self):
        '''监听 Redis 流'''
        while self.active:
            try:
                msgs = await self.redis.xread(
                    streams={self.stream_name: self.last_id},
                    count=10,
                    block=5000#阻塞等待的5秒
                )
                if msgs:
                    for _, messages in msgs:
                        for msg_id, msg_data in messages:
                            try:
                                data = json.loads(msg_data[b"data"].decode())
                            except Exception as e:
                                logger.info("❌ JSON decode error:", e)
                                continue

                            await self.ws.send_text(json.dumps(data))
                            self.last_id = msg_id
                            await self.redis.hset("stream:last_id", self.user_id, self.last_id)
                else:
                    await asyncio.sleep(0.2)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.info(f"Stream consume error: {e}")
                await asyncio.sleep(1)

    async def listen_user_input(self):
        '''监听用户输入'''
        async for msg_text in self.ws.iter_text():
            try:
                msg = json.loads(msg_text)
                task_id = msg.get("task_id")
                pdf_file = msg.get("pdf_file") 
                data = {
                    "pdf_file": pdf_file,
                    "stream_name": self.stream_name
                }

                app_work.send_task("app_tasks.ocr_pdf_task.pdf_to_md", args=[data], task_id=task_id)
                logger.info(f"✅ 调用 Celery 函数成功;task_id={task_id} ")

                await self.ws.send_text(json.dumps({"task_id": task_id, 
                                                    "status": "submitted"}))
            except Exception as e:
                logger.info(f"❌ 消息解析失败: {e}")
                await self.ws.send_text(json.dumps({"error": "Server error"}))



    async def cleanup(self):
        '''清理资源'''
        self.active = False
        if self.consumer_task:
            self.consumer_task.cancel()
            try:
                await self.consumer_task
            except asyncio.CancelledError:
                pass
        
        try:
            if not self.is_closed:
                await self.ws.close()
                self.is_closed = True
        except Exception as e:
            print(f"❌ WebSocket 关闭失败: {e}")
        
        print(f"❎ 用户 {self.user_id} WebSocket 已断开连接")