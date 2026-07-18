"""GPT-SoVITS API and reply-translation adapters."""
from pathlib import Path
import json
import subprocess
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
from core.openai_compat import bearer_headers, is_local_endpoint
from core.workers import BackgroundService


class TTSService(BackgroundService):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._local_process = None

    @staticmethod
    def _tts_url(base_url: str) -> str:
        endpoint = base_url.rstrip("/")
        # GPT-SoVITS exposes /tts at its service root. A common OpenAI-style
        # /v2 suffix would otherwise silently turn into the non-existent /v2/tts.
        if endpoint.endswith("/v2"):
            endpoint = endpoint.removesuffix("/v2")
        return endpoint if endpoint.endswith("/tts") else endpoint + "/tts"

    @staticmethod
    def _service_ready(base_url: str) -> bool:
        try:
            with urlopen(base_url.rstrip("/") + "/docs", timeout=2) as response:
                return 200 <= response.status < 500
        except (OSError, URLError):
            return False

    def _ensure_local_service(self, project_path, python_path, config_path, base_url):
        if self._service_ready(base_url):
            return
        project = Path(project_path)
        python = Path(python_path) if python_path else project / ".venv" / "Scripts" / "python.exe"
        config = Path(config_path)
        if not config.is_absolute():
            config = project / config
        if not project.is_dir() or not python.is_file() or not config.is_file():
            raise RuntimeError("本地 GPT-SoVITS 项目、Python 或 Noir 配置文件不存在")
        self._local_process = subprocess.Popen(
            [str(python), "api_v2.py", "-a", "127.0.0.1", "-p", "9880", "-c", str(config)],
            cwd=str(project), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for _ in range(120):
            if self._service_ready(base_url):
                return
            if self._local_process.poll() is not None:
                break
            time.sleep(1)
        raise RuntimeError("本地 GPT-SoVITS 启动失败或模型加载超时")

    def synthesize_gpt_sovits(
            self, text, base_url, api_key, reference_audio, prompt_text,
            output_path, speed=1.0, local_project="", local_python="", local_config=""):
        if not text.strip() or not base_url.strip() or not reference_audio:
            self.failed.emit("请完整配置 GPT-SoVITS 地址和参考音频")
            return False
        def work():
            if local_project:
                self._ensure_local_service(
                    local_project, local_python, local_config, base_url)
            payload = {
                "text": text.strip(), "text_lang": "ja",
                "ref_audio_path": str(reference_audio),
                "prompt_text": prompt_text.strip(), "prompt_lang": "ja",
                # Noir replies are deliberately short. Keep one request as
                # one continuous utterance so punctuation becomes a natural
                # pause rather than a boundary between separate WAV files.
                "text_split_method": "cut0", "batch_size": 1,
                "speed_factor": max(0.5, min(float(speed), 2.0)),
                "media_type": "wav", "streaming_mode": False,
                "parallel_infer": False,
            }
            request = Request(
                self._tts_url(base_url),
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8", **bearer_headers(api_key)},
            )
            with urlopen(request, timeout=600) as response:
                audio = response.read()
            if not audio or audio.startswith(b"{"):
                raise RuntimeError("GPT-SoVITS 未返回有效 WAV 音频")
            Path(output_path).write_bytes(audio)
            return str(output_path)
        return self.run(work)

    def synthesize_cloud(self, text, base_url, api_key, model, voice, output_path, speed=1.0):
        if not base_url or not model or not voice:
            self.failed.emit("请完整配置 TTS 的地址、模型和音色；本地服务可以不填 API Key")
            return False
        if not api_key and not is_local_endpoint(base_url):
            self.failed.emit("云端 TTS 需要 API Key；本地服务可以不填")
            return False

        def work():
            endpoint = base_url.rstrip("/")
            if not endpoint.endswith("/audio/speech"):
                endpoint += "/audio/speech"
            payload = {
                "model": model,
                "input": text,
                "voice": voice,
                "response_format": "wav",
                "speed": max(0.25, min(float(speed), 4.0)),
            }
            request = Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    **bearer_headers(api_key),
                },
            )
            with urlopen(request, timeout=90) as response:
                audio = response.read()
            if not audio:
                raise RuntimeError("云端 TTS 未返回音频数据")
            Path(output_path).write_bytes(audio)
            return str(output_path)

        return self.run(work)


class JapaneseTranslationService(BackgroundService):
    """Translate a visible Chinese reply into speech-only Japanese."""

    def translate(self, text, base_url, api_key, model):
        if not text.strip() or not base_url or not model:
            self.failed.emit("日文语音翻译缺少聊天模型配置")
            return False

        def work():
            endpoint = base_url.rstrip("/")
            if not endpoint.endswith("/chat/completions"):
                endpoint += "/chat/completions"
            payload = {
                "model": model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": (
                        "将用户给出的中文角色回复忠实翻译成自然、简短的日语。"
                        "保持原意、语气、称呼和句数，不增删信息。只输出日文译文，"
                        "不要解释、不要引号、不要中文、不要罗马音。")},
                    {"role": "user", "content": text.strip()},
                ],
            }
            request = Request(
                endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8", **bearer_headers(api_key)},
            )
            with urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
            translated = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if not translated:
                raise RuntimeError("聊天模型没有返回日文译文")
            return translated
        return self.run(work)
