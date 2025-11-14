# OcrPlus · PDF 转 Markdown（WebSocket + Redis Stream + Celery + PP-Structure + VLM）

将 PDF 转为高质量 Markdown，支持表格/图片结构化。通过 FastAPI WebSocket 实时返回结果，任务由 Celery 异步执行，消息经 Redis Stream 推送，OCR 使用 PaddleOCR PP-StructureV3，配合多模态大模型（阿里云 DashScope 兼容 OpenAI 协议）为图片补全文本描述。

- 技术栈：FastAPI · WebSocket · Celery · Redis Streams · PaddleOCR PPStructureV3 · OpenAI SDK(Async) · DashScope
- 关键特性：
  - WebSocket 实时通信，断线可续读（基于 Redis Stream last_id）
  - 异步任务执行，防阻塞（Celery）
  - OCR 保留文档结构，多模态补充图片说明
  - 结果分页返回，便于前端渲染与保存

---

## 目录结构

```
.
├── main.py                         # FastAPI 入口（WebSocket /ws/{user_id}）
├── celery_app.py                   # Celery 配置（Redis broker/backend，任务路由）
├── logger_conf.py                  # 日志配置
├── app_tasks/
│   ├── __init__.py
│   ├── util.py                     # 工具函数（保存 Base64 PDF）
│   ├── ocr_pdf_task.py             # Celery 任务：PDF→Markdown + 回写 Redis Stream
│   └── ocr_server.py               # OCR 主流程 + 多模态补充图片描述
├── websocket/
│   ├── __init__.py
│   └── websocket_handler.py        # WebSocket 会话：接收请求、消费 Redis Stream、转发消息
├── chanyi.conf
├── uvicorn_log_config.json
├── logs/                           # 日志目录（如需）
└── README.md
```

---

## 架构与数据流

1. 客户端连接 WebSocket：`/ws/{user_id}`，发送任务 JSON（包含 `task_id` 和 `pdf_file(base64)`）。
2. 服务器创建 Celery 任务：`app_tasks.ocr_pdf_task.pdf_to_md` 放入指定队列。
3. Celery Worker 执行：
   - 将 Base64 PDF 落地到 `tmp/{task_id}.pdf`
   - 使用 `PaddleOCR PPStructureV3` 解析结构化 Markdown；抽取图片并临时保存
   - 使用多模态模型（DashScope OpenAI 兼容接口）为图片生成 Markdown 描述
   - 合并成分页 Markdown 结果，写入 `Redis Stream: stream:task:{user_id}`
4. WebSocket 消费 Redis Stream，并将数据推送到对应连接。断线重连时将从 `stream:last_id` 记录的位置继续消费。

---

## 运行环境与依赖

- Python 3.9+（建议 3.10/3.11）
- Redis 7.x（默认本地：`localhost:6380`，密码：`123456`）
- PaddleOCR（PPStructureV3）
  - GPU：需要正确的 CUDA/CUDNN 与 `paddlepaddle-gpu`
  - CPU：可使用 `paddlepaddle`（注意性能）
- OpenAI Python SDK（>=1.x，使用 `AsyncOpenAI`）
- 其他：FastAPI、Uvicorn、Celery、redis-py（含 asyncio）、Pillow 等

示例安装（按需调整，省略具体版本）：
```bash
# 基础
pip install fastapi "uvicorn[standard]" celery redis "openai>=1.0.0" pillow

# Paddle（选择其一）
# CPU:
pip install paddlepaddle paddleocr
# GPU（根据 CUDA 版本选择合适的 wheel）:
# pip install paddlepaddle-gpu==<匹配你环境的版本> -f https://www.paddlepaddle.org.cn/whl/mkl/avx/stable.html
pip install paddleocr
```

Redis（Docker 示例）：
```yaml
# docker-compose.yml
version: "3.8"
services:
  redis:
    image: redis:7-alpine
    command: ["redis-server", "--requirepass", "123456", "--port", "6380"]
    ports:
      - "6380:6380"
```

---

## 配置

- Redis（在以下文件中使用了固定连接，生产建议改为环境变量）：
  - `websocket/websocket_handler.py`（async 客户端，db=2）
  - `celery_app.py`（broker db=0，backend db=1）
  - `app_tasks/ocr_pdf_task.py`（同步客户端，db=2）
- 多模态 API（DashScope OpenAI 兼容）：
  - `app_tasks/ocr_server.py` 中硬编码了示例密钥与 base_url：
    - `api_key="sk-xxxxxxxx"`、`base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"`
  - 强烈建议：使用环境变量管理机密
    - `export OPENAI_API_KEY=<your-dashscope-api-key>`
    - `export OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`
    - 并在代码中读取环境变量（后续可重构）
- 设备选择：
  - `app_tasks/ocr_server.py` 默认：`PPStructureV3(device="gpu:2")`
  - 如无该 GPU，请改为 `gpu:0` 或 `cpu`，例如：
    ```python
    PIPELINE = PPStructureV3(device="cpu")
    ```

---

## 启动步骤

1) 启动 Redis（确保 `localhost:6380` 可用，密码 `123456`）

2) 启动 Celery Worker（队列已在 `celery_app.py` 中配置）
```bash
# 单进程、solo 池便于调试
celery -A celery_app.app_work worker -l info \
  -Q task_celery_queue_ocet_work -n ocr_worker1@%h \
  --concurrency=1 --pool=solo
```

3) 启动 API（WebSocket 服务）
```bash
# 方式一：直接运行
python main.py

# 方式二：Uvicorn
uvicorn main:app --host 0.0.0.0 --port 8080
```

---

## WebSocket 接口

- URL：`ws://<host>:8080/ws/{user_id}`
- 客户端发送（JSON）：
  - `task_id`：字符串，唯一任务 ID（由客户端生成）
  - `pdf_file`：PDF 文件的 Base64 字符串
- 服务端返回：
  - 任务接收确认：
    ```json
    {"task_id": "<task_id>", "status": "submitted"}
    ```
  - 最终结果消息（经 Redis Stream 推送至当前 WebSocket）：
    ```json
    {
      "task_id": "<task_id>",
      "result": {
        "filename": "xxxx.pdf",
        "elapsed_time": "3.21s",
        "markdown": [
          {"page": 1, "markdown": "…该页 Markdown…"},
          {"page": 2, "markdown": "…该页 Markdown…"}
        ]
      }
    }
    ```

说明：
- WebSocket 连接会消费 Redis Stream：`stream:task:{user_id}`
- 位点记录在 Hash：`stream:last_id` 中（key 为 `user_id`），断线重连自动续读

---

## 客户端示例（Python）

```python
import asyncio
import base64
import json
import websockets  # pip install websockets

WS_URL = "ws://127.0.0.1:8080/ws/demo_user"
TASK_ID = "task-001"
PDF_PATH = "demo.pdf"

async def run():
    with open(PDF_PATH, "rb") as f:
        pdf_b64 = base64.b64encode(f.read()).decode("utf-8")

    async with websockets.connect(WS_URL) as ws:
        # 发送任务
        await ws.send(json.dumps({
            "task_id": TASK_ID,
            "pdf_file": pdf_b64
        }))
        # 持续接收消息（包括 submitted & 最终结果）
        async for msg in ws:
            data = json.loads(msg)
            print("recv:", json.dumps(data, ensure_ascii=False, indent=2))

asyncio.run(run())
```

---

## 开发与生产建议

- 将所有敏感配置改为环境变量（Redis 密码、API Key 等）
- 为 PaddleOCR 首次运行预热模型下载（避免 cold-start）
- 结合 Nginx/Ingress 暴露服务，限制上传大小
- 为 WebSocket 与 Celery 增加超时/重试策略与更丰富的状态回传（进度、失败原因）
- 记录与清理临时文件（当前会保存 `tmp/{task_id}.pdf` 并在 OCR 过程结束后删除 PDF 与图片）

---

## 故障排查

- Redis 连接失败：
  - 确认 6380 端口、密码 `123456`、各 DB（0/1/2）可用
  - 使用 `redis-cli -p 6380 -a 123456 PING`
- Celery 无法取到任务：
  - 确认队列名与路由：`task_celery_queue_ocet_work`
  - 确认 `include=["app_tasks.ocr_pdf_task"]`
- GPU/设备错误：
  - `PPStructureV3(device="gpu:2")` 若报错，改为 `gpu:0` 或 `cpu`
- PaddleOCR 模型下载超时：
  - 预先离线下载或配置代理；首次运行时间较久
- DashScope/大模型错误：
  - 校验 `OPENAI_API_KEY/OPENAI_BASE_URL`；留意速率限制与并发
- WebSocket 无消息：
  - 查看 worker 日志是否已 `xadd` 到 stream
  - 检查 `stream:last_id` 是否合理；必要时清空该 hash

---

## 许可与致谢

- OCR 能力来自 PaddleOCR（PPStructureV3）
- 多模态接口使用阿里云 DashScope（OpenAI 兼容模式）
- 本仓库 License 未明确标注，如需开源使用请先补充 LICENSE
