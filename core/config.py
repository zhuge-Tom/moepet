"""配置管理

支持分层配置：全局设置 + 角色专属设置。
位置记忆、窗口状态持久化。
"""

import json
import os
from pathlib import Path
from copy import deepcopy

DEFAULTS = {
    "current_character": "noir",
    "window": {
        "scale": 0.5,
        "always_on_top": True,
        "opacity": 1.0,
    },
    "behavior": {
        "click_action": "switch_sprite",
        "auto_idle": True,
        "idle_interval": 30,
    },
    "general": {
        "typing_speed": 40,
        "dialog_scale": 100,
        "auto_start": False,
    },
    "llm": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
        "stream": True,
        "post_processing": "",
        "ignore_format_error": True,
    },
    "asr": {
        "enabled": False, "model_path": "", "hotkey": "Ctrl+Alt+Space",
        "device": "cpu", "compute_type": "int8", "auto_send": True,
        "provider": "local", "base_url": "", "api_key": "",
        "model": "whisper-1", "language": "",
    },
    "tts": {
        "enabled": False, "model_path": "", "auto_play": True,
        "speed": 1.0, "volume": 1.0,
        "provider": "gpt_sovits_local", "base_url": "", "api_key": "",
        "local_api_url": "http://127.0.0.1:9880",
        "local_python": "", "local_config": "GPT_SoVITS/configs/noir_v2proplus.yaml",
        "remote_reference_audio": "",
        "translate_to_japanese": True,
        "model": "", "voice": "",
    },
    "screen_capture": {
        "hotkey": "Ctrl+Alt+O", "ocr_model_path": "", "keep_captures": False,
        "cloud_first": True,
        # Active observation is deliberately opt-in. Values are seconds.
        "auto_observe": False, "observe_min_interval": 300,
        "observe_max_interval": 900, "observe_cooldown": 600,
        # Upper bound for images sent to an optional vision provider.
        # OCR keeps the original capture for best text recognition.
        "vision_max_dimension": 1280,
    },
    "vision": {
        "enabled": False, "base_url": "", "api_key": "", "model": "",
        "allow_cloud": False,
    },
    "knowledge": {
        "enabled": True, "retrieval_count": 4, "max_context_chars": 3000,
    },
    "character_prompt": {
        "system_prompt": "你正在扮演 Noir。使用简短、自然、温柔的中文回答。保持安静、谨慎且真诚的气质，不要刻意卖萌、过度活泼、夸张热情或使用网络梗。面对陌生话题先温和确认；尊重边界，不强迫用户或自己做不舒服的事。回复通常控制在 100 字以内。",
        "format_prompt": "",
    },
    "position": {
        "pet_x": -1,
        "pet_y": -1,
        "dialog_x": -1,
        "dialog_y": -1,
    },
    "dialog": {
        "visible": False,
        "width": 480,
        "height": 200,
    },
}


class Config:
    """全局配置，支持路径式读写和自动保存"""

    def __init__(self, path: Path):
        self._path = path
        self._data = deepcopy(DEFAULTS)
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8-sig") as f:
                    stored = json.load(f)
                self._merge(self._data, stored)
                # Do not keep provider credentials in the project config file.
                migrated = False
                for section in ("llm", "vision", "asr", "tts"):
                    migrated = self._migrate_secret(section, stored) or migrated
                # A pasted document must never be treated as an API credential.
                for section in ("llm", "vision", "asr", "tts"):
                    key = self._data.get(section, {}).get("api_key", "")
                    if key and not self.is_valid_api_key(key):
                        self._data[section]["api_key"] = ""
                        migrated = True
                if migrated:
                    self.save()
            except (json.JSONDecodeError, OSError):
                pass

    def _migrate_secret(self, section: str, stored: dict) -> bool:
        value = stored.get(section, {}).get("api_key", "")
        if value and self.set_secret(section, value):
            self._data[section]["api_key"] = ""
            return True
        return False

    def set_secret(self, name: str, value: str) -> bool:
        """Persist secrets in the OS credential store when keyring is available."""
        try:
            import keyring
            keyring.set_password("Moepet", name, value)
            return True
        except (ImportError, RuntimeError):
            return False

    def get_secret(self, name: str) -> str:
        try:
            import keyring
            return keyring.get_password("Moepet", name) or ""
        except (ImportError, RuntimeError):
            return ""

    @staticmethod
    def is_valid_api_key(value: str) -> bool:
        """Reject pasted documents/control characters before a credential is saved."""
        return bool(value and len(value) <= 512 and not any(char.isspace() for char in value))

    @staticmethod
    def _merge(base: dict, override: dict):
        """递归合并，override 覆盖 base"""
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                Config._merge(base[k], v)
            else:
                base[k] = v

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # A replace avoids a partially written config during app shutdown.
        temp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, self._path)

    def get(self, *keys, default=None):
        """路径式获取: config.get('window', 'scale')"""
        node = self._data
        for k in keys:
            if isinstance(node, dict):
                node = node.get(k)
            else:
                return default
            if node is None:
                return default
        return node

    def set(self, *keys_and_value):
        """路径式设置: config.set('window', 'scale', 0.8)"""
        if len(keys_and_value) < 2:
            return
        *keys, value = keys_and_value
        node = self._data
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value

    @property
    def data(self) -> dict:
        return self._data

    @property
    def current_character(self) -> str:
        return self._data.get("current_character", "noir")

    def save_position(self, key: str, x: int, y: int):
        """记住窗口位置"""
        self.set("position", f"{key}_x", x)
        self.set("position", f"{key}_y", y)
        self.save()

    def get_position(self, key: str) -> tuple[int, int] | None:
        """读取窗口位置，未保存过则返回 None"""
        x = self.get("position", f"{key}_x", default=-1)
        y = self.get("position", f"{key}_y", default=-1)
        if x >= 0 and y >= 0:
            return (x, y)
        return None
