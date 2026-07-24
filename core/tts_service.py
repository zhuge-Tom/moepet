"""GPT-SoVITS API and reply-translation adapters."""
from pathlib import Path
from io import BytesIO
import json
import os
import re
import subprocess
import threading
import time
import wave
from urllib.error import URLError
from urllib.request import Request, urlopen
from PySide6.QtCore import QObject, QTimer, Signal
from core.openai_compat import bearer_headers, is_local_endpoint
from core.workers import BackgroundService


class AudioPlaybackService(QObject):
    """Play finalized WAV files on Windows without QtMultimedia."""

    completed = Signal(str)
    failed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._path = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._finish)

    def is_busy(self) -> bool:
        return self._busy

    def play(self, audio_path) -> bool:
        if self._busy:
            return False
        try:
            import wave
            import winsound

            path = str(Path(audio_path))
            with wave.open(path, "rb") as wav:
                duration_ms = max(1, round(wav.getnframes() * 1000 / wav.getframerate()))
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except (OSError, RuntimeError, ValueError, wave.Error) as exc:
            self.failed.emit(str(exc))
            return False
        self._path = path
        self._busy = True
        self.busy_changed.emit(True)
        self._timer.start(duration_ms + 120)
        return True

    def stop(self) -> None:
        self._timer.stop()
        if self._busy:
            try:
                import winsound
                winsound.PlaySound(None, 0)
            except (ImportError, RuntimeError):
                pass
        self._busy = False
        self._path = ""
        self.busy_changed.emit(False)

    def _finish(self) -> None:
        path = self._path
        self._path = ""
        self._busy = False
        self.busy_changed.emit(False)
        if path:
            self.completed.emit(path)


class TTSService(BackgroundService):
    fragment_ready = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self._local_process = None
        self._local_start_lock = threading.Lock()

    def shutdown_local(self):
        """Stop only the GPT-SoVITS process started by this application."""
        process = self._local_process
        self._local_process = None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    @staticmethod
    def _tts_url(base_url: str) -> str:
        endpoint = base_url.rstrip("/")
        # GPT-SoVITS exposes /tts at its service root. A common OpenAI-style
        # /v2 suffix would otherwise silently turn into the non-existent /v2/tts.
        if endpoint.endswith("/v2"):
            endpoint = endpoint.removesuffix("/v2")
        return endpoint if endpoint.endswith("/tts") else endpoint + "/tts"

    @staticmethod
    def _safe_local_speed(speed: float) -> float:
        """Avoid a CPU GPT-SoVITS bug that emits all-zero WAV above 1.01."""
        return max(0.5, min(float(speed or 1.0), 1.01))

    @staticmethod
    def _wav_has_signal(audio: bytes, minimum_peak: int = 32) -> bool:
        """Reject structurally valid WAV files whose PCM is effectively silent."""
        try:
            with wave.open(BytesIO(audio), "rb") as wav:
                sample_width = wav.getsampwidth()
                pcm = wav.readframes(wav.getnframes())
            if not pcm:
                return False
            if sample_width != 2:
                return any(pcm)
            samples = memoryview(pcm).cast("h")
            return any(abs(int(sample)) >= minimum_peak for sample in samples)
        except (OSError, ValueError, wave.Error):
            return False

    @staticmethod
    def _service_ready(base_url: str) -> bool:
        try:
            with urlopen(base_url.rstrip("/") + "/docs", timeout=2) as response:
                return 200 <= response.status < 500
        except (OSError, URLError):
            return False

    @staticmethod
    def _resolve_local_python(project_path, python_path):
        project = Path(project_path)
        if python_path:
            return Path(python_path)
        candidates = (
            project / "runtime" / "python.exe",
            project / ".venv" / "Scripts" / "python.exe",
            project / "venv" / "Scripts" / "python.exe",
        )
        return next((path for path in candidates if path.is_file()), candidates[0])

    @staticmethod
    def _local_environment(device="cuda", cpu_threads=4, reference_audio="", prompt_text=""):
        threads = str(max(1, min(int(cpu_threads or 4), 8)))
        env = {
            **os.environ,
            "OMP_NUM_THREADS": threads,
            "MKL_NUM_THREADS": threads,
            "OPENBLAS_NUM_THREADS": threads,
            "NUMEXPR_NUM_THREADS": threads,
            "TOKENIZERS_PARALLELISM": "false",
            "MOEPET_JA_ONLY": "1",
        }
        # api_v2.py consumes these at startup to calculate and retain the
        # fixed Noir reference cache.  Without them, merely opening /docs
        # preloads weights but the first real reply still pays reference-audio
        # analysis and decoder warm-up costs.
        if reference_audio:
            env["MOEPET_TTS_REFERENCE"] = str(reference_audio)
        if prompt_text:
            env["MOEPET_TTS_PROMPT"] = str(prompt_text)
        if device == "cpu":
            env["CUDA_VISIBLE_DEVICES"] = "-1"
        return env

    @staticmethod
    def _cpu_environment(cpu_threads=4, reference_audio="", prompt_text=""):
        """Backward-compatible CPU environment helper used by older callers/tests."""
        return TTSService._local_environment("cpu", cpu_threads, reference_audio, prompt_text)

    def _ensure_local_service(self, project_path, python_path, config_path, base_url,
                              cpu_threads=4, reference_audio="", prompt_text="", device="cuda"):
        if self._service_ready(base_url):
            return
        with self._local_start_lock:
            if self._service_ready(base_url):
                return
            project = Path(project_path)
            python = self._resolve_local_python(project, python_path)
            config = Path(config_path) if config_path else None
            if config and not config.is_absolute():
                config = project / config
            api_script = project / "api_v2.py"
            if not project.is_dir() or not python.is_file() or not api_script.is_file():
                raise RuntimeError("未找到 GPT-SoVITS 整合包、runtime\\python.exe 或 api_v2.py")
            if self._local_process is None or self._local_process.poll() is not None:
                command = [str(python), "api_v2.py", "-a", "127.0.0.1", "-p", "9880"]
                if config and config.is_file():
                    command.extend(["-c", str(config)])
                self._local_process = subprocess.Popen(
                    command,
                    cwd=str(project), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    env=self._local_environment(device, cpu_threads, reference_audio, prompt_text),
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            for _ in range(240):
                if self._service_ready(base_url):
                    return
                if self._local_process.poll() is not None:
                    break
                time.sleep(1)
        raise RuntimeError("本地 GPT-SoVITS 启动失败或模型加载超时")

    def prewarm_local(self, project_path, python_path, config_path, base_url,
                      cpu_threads=4, reference_audio="", prompt_text="", device="cuda"):
        """Load the CPU models during application startup without blocking the UI."""
        if not project_path or self._service_ready(base_url):
            return
        def warm():
            try:
                self._ensure_local_service(project_path, python_path, config_path,
                                           base_url, cpu_threads, reference_audio, prompt_text, device)
            except Exception as exc:
                self.failed.emit(str(exc))
        threading.Thread(target=warm, name="moepet-tts-prewarm", daemon=True).start()

    def synthesize_gpt_sovits(
            self, text, base_url, api_key, reference_audio, prompt_text,
            output_path, speed=1.0, local_project="", local_python="", local_config="",
            cpu_threads=4, streaming_mode=0, fragment_interval=0.18, device="cuda"):
        if not text.strip() or not base_url.strip() or not reference_audio:
            self.failed.emit("请完整配置 GPT-SoVITS 地址和参考音频")
            return False
        def work():
            if local_project:
                self._ensure_local_service(
                    local_project, local_python, local_config, base_url, cpu_threads,
                    reference_audio, prompt_text, device)
            requested_speed = (self._safe_local_speed(speed)
                               if local_project and device == "cpu" else
                               max(0.5, min(float(speed), 2.0)))
            base_payload = {
                "text_lang": "all_ja",
                "ref_audio_path": str(reference_audio),
                "prompt_text": prompt_text.strip(), "prompt_lang": "all_ja",
                # Noir replies are deliberately short. Keep one request as
                # one continuous utterance so punctuation becomes a natural
                # pause rather than a boundary between separate WAV files.
                "text_split_method": "cut0", "batch_size": 1,
                "speed_factor": requested_speed,
                # Each clause must be a finalized WAV. GPT-SoVITS HTTP
                # streaming writes zero RIFF/data lengths, which QMediaPlayer
                # treats as a zero-duration file. Low latency comes from the
                # clause queue below, not from an unfinished WAV container.
                "media_type": "wav", "streaming_mode": 0,
                "fragment_interval": max(0.1, min(float(fragment_interval), 0.5)),
                "parallel_infer": False,
            }
            parts = self._split_japanese_for_streaming(text) if streaming_mode else [text.strip()]
            output = Path(output_path)
            for index, part in enumerate(parts):
                payload = {**base_payload, "text": part}
                audio = b""
                for attempt in range(2):
                    if attempt:
                        payload["speed_factor"] = min(requested_speed, 1.0)
                    request = Request(
                        self._tts_url(base_url),
                        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                        headers={"Content-Type": "application/json; charset=utf-8", **bearer_headers(api_key)},
                    )
                    with urlopen(request, timeout=600) as response:
                        audio = response.read()
                    if (audio and not audio.startswith(b"{")
                            and self._wav_has_signal(audio)):
                        break
                if not self._wav_has_signal(audio):
                    raise RuntimeError("GPT-SoVITS 连续返回静音 WAV，已停止播放")
                part_path = (output if len(parts) == 1 else
                             output.with_name(f"{output.stem}-{index:02d}{output.suffix}"))
                part_path.write_bytes(audio)
                if len(parts) > 1:
                    self.fragment_ready.emit(str(part_path))
            return str(output) if len(parts) == 1 else None
        return self.run(work)

    @staticmethod
    def _split_japanese_for_streaming(text: str, target_chars: int = 6) -> list[str]:
        """Create natural, bounded clauses so playback can overlap synthesis."""
        clauses = [item.strip() for item in re.findall(r".+?[、。！？!?]|.+$", text.strip())
                   if item.strip()]
        parts, current = [], ""
        for clause in clauses:
            if current and len(current) + len(clause) > target_chars:
                parts.append(current)
                current = ""
            current += clause
            if len(current) >= target_chars or current.endswith(("。", "！", "？", "!", "?")):
                parts.append(current)
                current = ""
        if current:
            parts.append(current)
        return parts or [text.strip()]

    @staticmethod
    def _split_japanese_for_low_latency(text: str, target_chars: int = 8) -> list[str]:
        """Bound every CPU segment while preserving the complete Japanese text."""
        remaining = text.strip()
        parts = []
        while len(remaining) > target_chars:
            window = remaining[:target_chars]
            boundary = max(*(window.rfind(mark) for mark in "、。！？!?"))
            cut = boundary + 1 if boundary >= max(3, target_chars // 2) else target_chars
            parts.append(remaining[:cut])
            remaining = remaining[cut:]
        if remaining:
            parts.append(remaining)
        return parts

    @staticmethod
    def _speech_url(base_url: str) -> str:
        endpoint = base_url.rstrip("/")
        return endpoint if endpoint.endswith("/audio/speech") else endpoint + "/audio/speech"

    def synthesize_cloud(self, text, base_url, api_key, model, voice, output_path,
                         speed=1.0, response_format="wav"):
        if not base_url or not model or not voice:
            self.failed.emit("请完整配置 TTS 的地址、模型和音色；本地服务可以不填 API Key")
            return False
        if not api_key and not is_local_endpoint(base_url):
            self.failed.emit("云端 TTS 需要 API Key；本地服务可以不填")
            return False

        def work():
            endpoint = self._speech_url(base_url)
            payload = {
                "model": model,
                "input": text,
                "voice": voice,
                "response_format": response_format or "wav",
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

    @staticmethod
    def _clean_speech_translation(text: str) -> str:
        """Remove reasoning wrappers while preserving the complete translation."""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        return text.strip(" \t\r\n\"'「」『』")

    @staticmethod
    def _short_speech_translation(text: str, limit: int = 18) -> str:
        """Keep speech translation to one compact sentence for CPU latency."""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        text = text.strip(" \t\r\n\"'「」『』")
        if not text:
            return ""
        sentence = re.match(r".*?[。！？!?](?:[」』\"']|\s|$)", text)
        text = sentence.group(0).strip(" \t\r\n\"'「」『』") if sentence else text
        if len(text) <= limit:
            return text
        return text[:limit].rstrip("、。！？!?") + "。"

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
                        "将用户给出的中文角色回复完整翻译成自然、简短的日语。"
                        "保留全部句子和信息，不得总结、删减或截断。"
                        "只输出日文译文；不要思考过程、解释、引号、中文或罗马音。")},
                    {"role": "user", "content": text.strip()},
                ],
            }
            request = Request(
                endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8", **bearer_headers(api_key)},
            )
            with urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
            translated = self._clean_speech_translation(
                data.get("choices", [{}])[0].get("message", {}).get("content", ""))
            if not translated:
                raise RuntimeError("聊天模型没有返回日文译文")
            return translated
        return self.run(work)
