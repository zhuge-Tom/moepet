"""配置管理

支持分层配置：全局设置 + 角色专属设置。
位置记忆、窗口状态持久化。
"""

import json
from pathlib import Path
from copy import deepcopy

DEFAULTS = {
    "current_character": "nuowa",
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
    "character_prompt": {
        "system_prompt": "你是一个可爱的桌面宠物助手，用简短、活泼的语气回复。回复请控制在100字以内。",
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
                with open(self._path, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                self._merge(self._data, stored)
            except (json.JSONDecodeError, OSError):
                pass

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
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

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
        return self._data.get("current_character", "nuowa")

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
