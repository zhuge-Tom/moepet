"""Explicit single-image vision requests for OpenAI-compatible local or cloud APIs."""
import base64
import json
from pathlib import Path
from urllib.request import Request, urlopen
from core.workers import BackgroundService


class VisionService(BackgroundService):
    def describe(self, image_path: Path, base_url: str, api_key: str, model: str, ocr_text=""):
        if not base_url or not model:
            self.failed.emit("请先配置视觉模型服务；截图不会被自动上传")
            return False
        def work():
            encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
            body = {"model": model, "messages": [{"role": "user", "content": [
                {"type": "text", "text": f"描述这张截图。OCR 文本：{ocr_text}"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
            ]}]}
            request = Request(base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
            with urlopen(request, timeout=90) as response:
                return json.loads(response.read())["choices"][0]["message"]["content"]
        return self.run(work)
