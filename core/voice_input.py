"""Push-to-talk capture with optional sounddevice dependency."""

import queue
import wave
from pathlib import Path

from PySide6.QtCore import QObject, Signal


class PushToTalkRecorder(QObject):
    started = Signal()
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stream = None
        self._chunks = queue.Queue()
        self._sample_rate = 16000

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self) -> bool:
        if self.recording:
            return False
        try:
            import sounddevice as sd
        except ImportError:
            self.failed.emit("未安装 sounddevice；请安装可选语音依赖")
            return False
        self._chunks = queue.Queue()
        try:
            self._stream = sd.InputStream(
                samplerate=self._sample_rate, channels=1, dtype="int16",
                callback=lambda data, _frames, _time, _status: self._chunks.put(data.copy()),
            )
            self._stream.start()
        except Exception as exc:
            self._stream = None
            self.failed.emit(f"无法使用麦克风：{exc}")
            return False
        self.started.emit()
        return True

    def stop(self, output_path: Path) -> bool:
        if not self.recording:
            return False
        stream, self._stream = self._stream, None
        try:
            stream.stop()
            stream.close()
            frames = []
            while not self._chunks.empty():
                frames.append(self._chunks.get_nowait().tobytes())
            if not frames:
                self.failed.emit("没有录到音频")
                return False
            with wave.open(str(output_path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(self._sample_rate)
                wav.writeframes(b"".join(frames))
            self.completed.emit(str(output_path))
            return True
        except Exception as exc:
            self.failed.emit(f"保存录音失败：{exc}")
            return False

    def cancel(self) -> None:
        """Discard an in-progress push-to-talk recording without emitting audio."""
        if not self.recording:
            return
        stream, self._stream = self._stream, None
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass
        self._chunks = queue.Queue()
