"""CosyVoice adapter. The dependency and model are deliberately user supplied."""
from pathlib import Path
import json
from urllib.request import Request, urlopen
from core.openai_compat import bearer_headers, is_local_endpoint
from core.workers import BackgroundService


class TTSService(BackgroundService):
    def synthesize(self, text, model_path, reference_audio, output_path, speed=1.0):
        if not model_path or not Path(model_path).exists() or not Path(reference_audio).exists():
            self.failed.emit("请配置 CosyVoice 模型目录和已授权的参考音频")
            return False
        def work():
            try:
                from cosyvoice.cli.cosyvoice import CosyVoice
                import torchaudio
            except ImportError as exc:
                raise RuntimeError("未安装 CosyVoice 及其依赖") from exc
            voice = CosyVoice(model_path)
            for item in voice.inference_zero_shot(text, "", reference_audio, stream=False, speed=speed):
                torchaudio.save(str(output_path), item["tts_speech"], voice.sample_rate)
                return str(output_path)
            raise RuntimeError("CosyVoice 未生成音频")
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
