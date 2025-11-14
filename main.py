from fastapi import FastAPI, WebSocket
from websocket.websocket_handler import WebSocketHandler


app = FastAPI()

@app.websocket("/ws/{user_id}")
async def ws(user_id: str, websocket: WebSocket):
    handler = WebSocketHandler(websocket,user_id)
    await handler.start()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)