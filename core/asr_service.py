"""Optional local faster-whisper transcription service."""
import json
import mimetypes
from pathlib import Path
from urllib.request import Request, urlopen
from core.openai_compat import bearer_headers, is_local_endpoint
from core.workers import BackgroundService


class ASRService(BackgroundService):
    def transcribe(self, audio_path: Path, model_path: str, device="cpu", compute_type="int8"):
        if not model_path or not Path(model_path).exists():
            self.failed.emit("请在设置中配置有效的 faster-whisper 模型目录")
            return False
        def work():
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError("未安装 faster-whisper；请安装可选语音依赖") from exc
            model = WhisperModel(model_path, device=device, compute_type=compute_type)
            segments, info = model.transcribe(str(audio_path), vad_filter=True)
            return {"text": "".join(s.text for s in segments).strip(), "language": info.language}
        return self.run(work)

    def transcribe_cloud(self, audio_path: Path, base_url: str, api_key: str,
                         model: str, language: str = ""):
        """Transcribe one WAV file through an OpenAI-compatible endpoint."""
        if not base_url or not model:
            self.failed.emit("请完整配置 ASR 的地址和模型；本地服务可以不填 API Key")
            return False
        if not api_key and not is_local_endpoint(base_url):
            self.failed.emit("云端 ASR 需要 API Key；本地服务可以不填")
            return False

        def work():
            boundary = "----moepet-asr-boundary"
            fields = {"model": model}
            if language:
                fields["language"] = language
            chunks = []
            for name, value in fields.items():
                chunks.extend((
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                    str(value).encode("utf-8"), b"\r\n",
                ))
            mime = mimetypes.guess_type(audio_path.name)[0] or "audio/wav"
            chunks.extend((
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="file"; filename="{audio_path.name}"\r\n'.encode(),
                f"Content-Type: {mime}\r\n\r\n".encode(),
                audio_path.read_bytes(), b"\r\n",
                f"--{boundary}--\r\n".encode(),
            ))
            endpoint = base_url.rstrip("/")
            if not endpoint.endswith("/audio/transcriptions"):
                endpoint += "/audio/transcriptions"
            request = Request(endpoint, data=b"".join(chunks), headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                **bearer_headers(api_key),
            })
            with urlopen(request, timeout=90) as response:
                data = json.loads(response.read())
            return {"text": str(data.get("text", "")).strip(), "language": language}

        return self.run(work)
