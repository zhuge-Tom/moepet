"""Small, editable provider presets for Moepet's OpenAI-compatible forms."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderPreset:
    key: str
    label: str
    base_url: str
    default_model: str


@dataclass(frozen=True)
class TTSPreset:
    key: str
    label: str
    base_url: str
    default_model: str
    default_voice: str
    note: str = ""


CHAT_PRESETS = (
    ProviderPreset("custom", "自定义 OpenAI-compatible 服务", "", ""),
    ProviderPreset("ollama", "Ollama（本地，无需 API Key）", "http://localhost:11434/v1", "qwen3:8b"),
    ProviderPreset("deepseek", "DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat"),
    ProviderPreset("openai", "OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
)

VISION_PRESETS = (
    ProviderPreset("custom", "自定义 OpenAI-compatible 视觉服务", "", ""),
    ProviderPreset("ollama", "Ollama（本地，无需 API Key）", "http://localhost:11434/v1", "qwen3-vl:8b"),
    ProviderPreset("openai", "OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
)

TTS_PRESETS = (
    TTSPreset("custom", "自定义 OpenAI 兼容服务", "", "", ""),
    TTSPreset("openai", "OpenAI", "https://api.openai.com/v1",
              "gpt-4o-mini-tts", "alloy"),
    TTSPreset("siliconflow", "SiliconFlow（硅基流动）",
              "https://api.siliconflow.cn/v1", "FunAudioLLM/CosyVoice2-0.5B",
              "FunAudioLLM/CosyVoice2-0.5B:anna", "支持中文、英文、日文和韩文"),
    TTSPreset("groq", "Groq（英语 / 阿拉伯语）",
              "https://api.groq.com/openai/v1", "canopylabs/orpheus-v1-english",
              "autumn", "Orpheus 当前仅适合英语或阿拉伯语"),
    TTSPreset("local", "LocalAI / 自建兼容服务",
              "http://127.0.0.1:8080/v1", "", ""),
)


def preset_key_for_url(base_url: str, presets: tuple[ProviderPreset, ...]) -> str:
    """Recognize known endpoints while leaving edited URLs as custom."""
    endpoint = base_url.rstrip("/").lower()
    for preset in presets:
        if preset.base_url and endpoint == preset.base_url.rstrip("/").lower():
            return preset.key
    return "custom"


def preset_by_key(key: str, presets: tuple[ProviderPreset, ...]) -> ProviderPreset:
    for preset in presets:
        if preset.key == key:
            return preset
    return presets[0]
