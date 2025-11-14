import asyncio
import base64
import os
from pathlib import Path
import re
import time
from openai import AsyncOpenAI
from paddleocr import PPStructureV3
from logger_conf import logger

PIPELINE = PPStructureV3(device="gpu:2")

# ------------------ 工具方法 ------------------
def image_to_base64(image_path: str) -> str:
    if not Path(image_path).exists():
        logger.error(f"文件 {image_path} 不存在")
        return None
    with open(image_path, "rb") as f:
        base =  base64.b64encode(f.read()).decode("utf-8")
    os.remove(image_path)
    return base
    


async def describe_image_with_vlm(image_path: str, client: AsyncOpenAI) -> str:
    b64 = image_to_base64(image_path)
    if b64 is None:
        return ""
    prompt = "Please understand the content of the image and extract the key points using pure Markdown to avoid redundant and meaningless output."

    for i in range(5):  
        try:
            resp = await client.chat.completions.create(
                model="qwen-vl-plus",
                messages=[
                    {"role": "system", "content": [{"type": "text", "text": "You are a helpful assistant."}]},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                        {"type": "text", "text": prompt}
                    ]}
                ]
            )
            msg = resp.choices[0].message.content
            index = msg.find("```markdown")
            msg = msg[index+len("```markdown"):] if index >= 0 else msg
            end = msg.find("```")
            msg = msg[:end] if end >= 0 else msg

            return f"\n{msg}\n\n"
        except Exception as e:
            logger.error(f"VLM 调用失败: {e}, retry...\n次数{i}")
            await asyncio.sleep(3)
    return ""


def replace_div_with_image_path(text: str, img_desc: str) -> str:
    div_pattern = re.compile(r'<div[^>]*>.*?</div>', re.S)
    def replace(match):
        div_content = match.group(0)
        if re.search(r'<img[^>]*src="([^"]+)"', div_content):
            return img_desc
        return div_content

    return div_pattern.sub(replace, text)

# ------------------ 任务处理 ------------------
async def _handle_task(pdf_path: str, pipeline):
    start = time.time()
    logger.info("模型处理中...")
    output = pipeline.predict(input=str(pdf_path))
    os.remove(pdf_path)
    result = []
    markdown_list = [res.markdown for res in output]

    img_paths = []
    for data in markdown_list:
        markdown_images = data.get("markdown_images", {})
        for path, image in markdown_images.items():
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(file_path)
            img_paths.append(str(file_path))
        result.append({
            "page": data["page_index"],
            "markdown": data["markdown_texts"]
        })
    logger.info(f"模型OCR耗时{time.time()-start:.2f}")
    logger.info(f"开始执行多模态 共计{len(img_paths)}张图片")
    async with AsyncOpenAI(api_key="sk-511eb564f0e44080a2e007fda64bdb32", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1") as client:
        image_md = await asyncio.gather(*[describe_image_with_vlm(p, client) for p in img_paths])
    logger.info(f"多模态执行完成")
        
    res = []
    for item in result:
        md = item["markdown"]
        page = item["page"]
        for i, img_path in enumerate(img_paths):
            if img_path in md:
                md = replace_div_with_image_path(md, image_md[i])
        res.append({"page": page, "markdown": md})

    return {
        "filename": os.path.basename(pdf_path),
        "elapsed_time": f"{time.time() - start:.2f}s",
        "markdown": res
    }
async def ocr_pdf_to_md(pdf_path):
    result = await _handle_task(pdf_path,PIPELINE)
    return result




