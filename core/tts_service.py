"""CosyVoice adapter. The dependency and model are deliberately user supplied."""
from pathlib import Path
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
