"""Small, editable provider presets for Moepet's OpenAI-compatible forms."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderPreset:
    key: str
    label: str
    base_url: str
    default_model: str


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
