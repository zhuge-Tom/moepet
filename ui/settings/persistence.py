"""Persistence boundary for settings form data.

Widgets collect a draft; this module validates secrets, writes them through the
configuration store, and returns the sanitized payload for runtime reloading.
"""

import json
from pathlib import Path


SECRET_SECTIONS = ("llm", "vision", "asr", "tts")


def apply_settings(config, settings: dict) -> tuple[dict | None, str | None]:
    """Persist a settings draft or return a user-facing validation message."""
    for section in SECRET_SECTIONS:
        key = settings.get(section, {}).get("api_key", "")
        if key and not config.is_valid_api_key(key):
            return None, (
                "API Key 不能包含空格或换行，且长度不能超过 512 个字符。\n"
                "请只粘贴服务商提供的完整密钥。"
            )

    for section in SECRET_SECTIONS:
        section_data = settings.get(section)
        if not isinstance(section_data, dict):
            continue
        key = section_data.pop("api_key", "")
        if key:
            if not config.set_secret(section, key):
                # Keep optional providers usable on systems without keyring.
                section_data["api_key"] = key
        else:
            stored_key = config.get_secret(section) or config.get(section, "api_key", default="")
            if stored_key:
                section_data["api_key"] = stored_key

    for section, data in settings.items():
        # Role activation remains PetManager's responsibility because it also
        # resets per-role state and chat history.
        if section == "current_character":
            continue
        if isinstance(data, dict):
            for key, value in data.items():
                config.set(section, key, value)
        else:
            config.set(section, data)
    config.save()
    return settings, None


def save_character_prompt(path: Path, system_prompt: str, format_prompt: str) -> None:
    """Persist the role-owned prompt without changing unrelated character data."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return
    data["character_prompt"] = {
        "system_prompt": system_prompt,
        "format_prompt": format_prompt,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
