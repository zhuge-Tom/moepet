"""Background capability probes used by settings pages.

The window supplies only current form values.  Network and dependency checks
live here so page widgets stay focused on presentation and configuration.
"""

import json
import threading
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, Signal
from core.openai_compat import bearer_headers, model_discovery_urls


class ProbeRunner(QObject):
    finished = Signal(str, bool, str)

    def run(self, key: str, probe) -> None:
        def task():
            try:
                ok, message = probe()
            except Exception as exc:
                ok, message = False, f"测试失败：{type(exc).__name__}: {str(exc)[:120]}"
            self.finished.emit(key, bool(ok), str(message))

        threading.Thread(target=task, name=f"moepet-{key}-probe", daemon=True).start()


class ModelDiscoveryRunner(QObject):
    """Fetch provider models without freezing the settings dialog."""

    finished = Signal(str, bool, str, list)

    def run(self, key: str, base_url: str, api_key: str) -> None:
        def task():
            try:
                models = discover_models(base_url, api_key)
                ok = bool(models)
                message = f"发现 {len(models)} 个可选模型" if ok else "没有从服务返回可选模型"
            except Exception as exc:
                ok, message, models = False, f"获取模型失败：{type(exc).__name__}: {str(exc)[:120]}", []
            self.finished.emit(key, ok, message, models)

        threading.Thread(target=task, name=f"moepet-{key}-models", daemon=True).start()


def discover_models(base_url: str, api_key: str) -> list[str]:
    """Discover OpenAI-compatible or Ollama model names from one endpoint."""
    if not base_url.strip():
        raise ValueError("请先填写服务地址")
    errors = []
    for url in model_discovery_urls(base_url):
        try:
            request = Request(url, headers=bearer_headers(api_key))
            with urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
            if url.endswith("/api/tags"):
                entries = data.get("models", [])
                models = [item.get("name", "") for item in entries if isinstance(item, dict)]
            else:
                entries = data.get("data") or data.get("models") or []
                models = [
                    item.get("id") or item.get("name", "")
                    for item in entries if isinstance(item, dict)
                ]
            models = sorted({str(model).strip() for model in models if str(model).strip()})
            if models:
                return models
            errors.append(f"{url} 未返回模型")
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("；".join(errors))


def probe_local_module(module: str, model_path: str = "") -> tuple[bool, str]:
    if model_path and not Path(model_path).is_dir():
        return False, "模型目录不存在或不可访问"
    __import__(module)
    return True, "本地依赖和模型目录可用"


def probe_http_endpoint(url: str, api_key: str, payload: dict | None = None) -> tuple[bool, str]:
    if not url.strip():
        return False, "请先填写服务地址"
    headers = {"Content-Type": "application/json"}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    request = Request(url, data=json.dumps(payload or {}).encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(request, timeout=20) as response:
            if 200 <= response.status < 300:
                return True, "服务连接和凭据验证成功"
            return False, f"服务返回 HTTP {response.status}"
    except HTTPError as exc:
        if exc.code in (401, 403):
            return False, "服务可达，但 API Key 无效或没有权限"
        if exc.code in (400, 405):
            return True, "服务可达并已响应测试请求"
        return False, f"服务返回 HTTP {exc.code}"
    except URLError as exc:
        return False, f"无法连接服务：{getattr(exc, 'reason', exc)}"


def probe_cosyvoice(model_path: str) -> tuple[bool, str]:
    if not model_path or not Path(model_path).is_dir():
        return False, "请先填写可访问的 CosyVoice 模型目录"
    __import__("cosyvoice.cli.cosyvoice")
    __import__("torchaudio")
    return True, "CosyVoice 依赖和模型目录可用"


def probe_ocr() -> tuple[bool, str]:
    from rapidocr_onnxruntime import RapidOCR
    RapidOCR()
    return True, "本地 OCR 引擎初始化成功"
