"""Optional local faster-whisper transcription service."""
from pathlib import Path
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
