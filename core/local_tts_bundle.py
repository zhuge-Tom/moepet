"""Detection helpers for a user-managed GPT-SoVITS integrated package.

Moepet intentionally does not ship a large inference bundle.  Users select
their extracted GPT-SoVITS directory and this module locates the runtime in a
small, deterministic way before the UI or TTS service starts it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import os


@dataclass(frozen=True)
class LocalTtsBundle:
    root: Path
    python: Path | None
    api_script: Path | None
    config: Path | None

    @property
    def ready(self) -> bool:
        return bool(self.root.is_dir() and self.python and self.api_script)

    @property
    def message(self) -> str:
        if not self.root.is_dir():
            normalized = str(self.root).replace("\\", "/").lower()
            if normalized.endswith("vendor/gpt_sovits_cpu"):
                return "CPU 兼容包尚未安装；点击“安装引导”完成下载"
            return "尚未选择 GPT-SoVITS 整合包目录"
        if not self.python:
            return "未找到 runtime\\python.exe；请选择整合包解压后的根目录"
        if not self.api_script:
            return "找到 Python，但目录中没有 api_v2.py"
        if self.config:
            return "整合包已就绪，可使用 GPU 推理"
        return "整合包已就绪；将使用整合包默认推理配置"


@dataclass(frozen=True)
class NoirVoiceAssets:
    root: Path
    gpt_weight: Path | None
    sovits_weight: Path | None
    reference_audio: Path | None
    reference_text: str
    reference_text_zh: str

    @property
    def ready(self) -> bool:
        return bool(self.gpt_weight and self.sovits_weight and self.reference_audio
                    and self.reference_text.strip())

    @property
    def message(self) -> str:
        missing = []
        if not self.gpt_weight:
            missing.append("Noir GPT 权重")
        if not self.sovits_weight:
            missing.append("Noir SoVITS 权重")
        if not self.reference_audio:
            missing.append("参考音频")
        if not self.reference_text.strip():
            missing.append("参考文本")
        return "Noir 语音资源已就绪" if not missing else "缺少：" + "、".join(missing)


def inspect_local_tts_bundle(path: str, config_path: str = "") -> LocalTtsBundle:
    """Find standard integrated-package files without recursively scanning disks."""
    # Path() means the current working directory, which can accidentally
    # contain Moepet's own .venv. An empty user selection must stay empty.
    if not path:
        return LocalTtsBundle(root=Path("__no_gpt_sovits_bundle_selected__"),
                              python=None, api_script=None, config=None)
    raw = Path(path).expanduser()
    root = raw
    if raw.name.lower() == "python.exe":
        # Accept a saved runtime path from older Moepet settings.
        root = raw.parent.parent if raw.parent.name.lower() == "runtime" else raw.parent
    root = root.resolve() if root.exists() else root
    python_candidates = (
        root / "runtime" / "python.exe",
        root / ".venv" / "Scripts" / "python.exe",
        root / "venv" / "Scripts" / "python.exe",
    )
    python = next((candidate for candidate in python_candidates if candidate.is_file()), None)
    api_candidates = (root / "api_v2.py", root / "api.py")
    api_script = next((candidate for candidate in api_candidates if candidate.is_file()), None)
    config = Path(config_path).expanduser() if config_path else None
    if config and not config.is_absolute():
        config = root / config
    if config and not config.is_file():
        config = None
    return LocalTtsBundle(root=root, python=python, api_script=api_script, config=config)


def inspect_noir_voice_assets(project_root: str | Path) -> NoirVoiceAssets:
    """Read the project-owned Noir assets required for a complete TTS setup."""
    root = Path(project_root) / "voice_assets" / "noir"
    gpt = root / "noir-e15.ckpt"
    sovits = root / "noir_e8_s968.pth"
    audio = root / "reference.wav"
    text_path = root / "reference.txt"
    text_zh_path = root / "reference_zh.txt"
    return NoirVoiceAssets(
        root=root,
        gpt_weight=gpt if gpt.is_file() else None,
        sovits_weight=sovits if sovits.is_file() else None,
        reference_audio=audio if audio.is_file() else None,
        reference_text=text_path.read_text(encoding="utf-8").strip() if text_path.is_file() else "",
        reference_text_zh=(text_zh_path.read_text(encoding="utf-8").strip()
                           if text_zh_path.is_file() else ""),
    )


def make_noir_inference_config(bundle: LocalTtsBundle, assets: NoirVoiceAssets,
                               device: str = "cuda") -> Path:
    """Create a portable, absolute-path config for the selected package.

    The integrated package owns its pretrained HuBERT/BERT models, while
    Moepet owns the character weights and reference audio.  A generated config
    keeps those responsibilities separate and works no matter where either
    folder was extracted.
    """
    if not bundle.ready:
        raise RuntimeError(bundle.message)
    if not assets.ready:
        raise RuntimeError(assets.message)
    pretrained = bundle.root / "GPT_SoVITS" / "pretrained_models"
    bert = pretrained / "chinese-roberta-wwm-ext-large"
    hubert = pretrained / "chinese-hubert-base"
    if not hubert.is_dir():
        raise RuntimeError("整合包缺少 GPT_SoVITS/pretrained_models/chinese-hubert-base")
    quote = lambda value: '"' + str(value).replace('\\', '/').replace('"', '\\"') + '"'
    resolved_device = "cpu" if device == "cpu" else "cuda"
    is_half = "false" if resolved_device == "cpu" else "true"
    bert_value = quote(bert) if bert.is_dir() else '""'
    stamp = hashlib.sha256(
        f"{bundle.root}|{assets.root}|{resolved_device}".encode("utf-8")).hexdigest()[:16]
    cache = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Moepet" / "tts_configs"
    cache.mkdir(parents=True, exist_ok=True)
    config = cache / f"noir-{stamp}.yaml"
    config.write_text(
        "custom:\n"
        # Japanese synthesis does not need the Chinese BERT.  Leave the value
        # empty when an otherwise valid lightweight package omits it; the
        # package then applies its own default for Chinese requests.
        f"  bert_base_path: {bert_value}\n"
        f"  cnhuhbert_base_path: {quote(hubert)}\n"
        f"  device: {resolved_device}\n"
        f"  is_half: {is_half}\n"
        f"  t2s_weights_path: {quote(assets.gpt_weight)}\n"
        "  version: v2ProPlus\n"
        f"  vits_weights_path: {quote(assets.sovits_weight)}\n",
        encoding="utf-8")
    return config
