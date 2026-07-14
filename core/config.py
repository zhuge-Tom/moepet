"""
全局配置管理
"""

import json
from pathlib import Path

DEFAULT_CONFIG = {
    "current_character": "nuowa",
    "window": {
        "scale": 1.0,
        "offset_x": 100,
        "offset_y": 100,
    },
    "behavior": {
        "click_action": "switch_sprite",   # 点击行为: switch_sprite / bounce / none
        "auto_idle": True,                  # 自动待机动画
        "always_on_top": True,              # 始终在最前
    }
}


class Config:
    """全局配置管理"""

    def __init__(self, path: Path):
        self.path = path
        self.data = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                self.data.update(loaded)

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get(self, *keys, default=None):
        """按路径获取配置，如 config.get('window', 'scale')"""
        val = self.data
        for key in keys:
            if isinstance(val, dict):
                val = val.get(key)
            else:
                return default
        return val if val is not None else default

    @property
    def current_character(self) -> str:
        return self.data.get("current_character", "nuowa")
