"""Explicit single-image vision requests for OpenAI-compatible local or cloud APIs."""
import base64
import json
from pathlib import Path
from urllib.request import Request, urlopen
from core.workers import BackgroundService
from core.openai_compat import bearer_headers, chat_completions_url


class VisionService(BackgroundService):
    def describe(self, image_path: Path, base_url: str, api_key: str, model: str, ocr_text="",
                 max_dimension: int = 0):
        if not base_url or not model:
            self.failed.emit("请先配置视觉模型服务；截图不会被自动上传")
            return False
        def work():
            encoded, mime = image_data_url_payload(image_path, max_dimension)
            body = {"model": model, "messages": [{"role": "user", "content": [
                {"type": "text", "text": f"描述这张截图。OCR 文本：{ocr_text}"},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
            ]}]}
            headers = {"Content-Type": "application/json", **bearer_headers(api_key)}
            request = Request(
                chat_completions_url(base_url), data=json.dumps(body).encode(), headers=headers)
            with urlopen(request, timeout=90) as response:
                return json.loads(response.read())["choices"][0]["message"]["content"]
        return self.run(work)


def image_data_url_payload(image_path: Path, max_dimension: int = 0) -> tuple[str, str]:
    """Encode a bounded JPEG for vision APIs, preserving original when disabled."""
    max_dimension = int(max_dimension or 0)
    if max_dimension <= 0:
        return base64.b64encode(image_path.read_bytes()).decode("ascii"), "image/png"
    try:
        from PIL import Image
    except ImportError:
        return base64.b64encode(image_path.read_bytes()).decode("ascii"), "image/png"
    from io import BytesIO
    with Image.open(image_path) as image:
        image = image.convert("RGB")
        image.thumbnail((max_dimension, max_dimension))
        output = BytesIO()
        image.save(output, format="JPEG", quality=85, optimize=True)
    return base64.b64encode(output.getvalue()).decode("ascii"), "image/jpeg"
