"""Optional offline OCR; screenshots are processed only when explicitly supplied."""
from pathlib import Path
from core.workers import BackgroundService


class OcrService(BackgroundService):
    def recognize(self, image_path: Path):
        def work():
            try:
                from rapidocr_onnxruntime import RapidOCR
            except ImportError as exc:
                raise RuntimeError("未安装 rapidocr-onnxruntime；请安装可选 OCR 依赖") from exc
            result, _ = RapidOCR()(str(image_path))
            return "\n".join(item[1] for item in (result or []))
        return self.run(work)
