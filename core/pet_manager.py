"""
角色管理器 - 负责加载、切换角色
"""

import json
from pathlib import Path

from core.pet_window import PetWindow


class PetManager:
    """管理所有角色实例"""

    def __init__(self, characters_dir: Path, config: dict):
        self.characters_dir = characters_dir
        self.config = config
        self.windows: dict[str, PetWindow] = {}
        self._init_characters()

    def _init_characters(self):
        """扫描所有角色目录"""
        if not self.characters_dir.exists():
            return

        for char_dir in self.characters_dir.iterdir():
            if char_dir.is_dir():
                char_config_path = char_dir / "config.json"
                if char_config_path.exists():
                    with open(char_config_path, "r", encoding="utf-8") as f:
                        char_cfg = json.load(f)
                    self.windows[char_dir.name] = PetWindow(char_dir, char_cfg)

    def show_current(self):
        """显示当前角色"""
        current = self.config.get("current_character", "nuowa")
        if current in self.windows:
            self.windows[current].show()
        else:
            print(f"[Moepet] 角色 '{current}' 未找到，可用角色: {list(self.windows.keys())}")

    def show(self, name: str):
        """显示指定角色"""
        if name in self.windows:
            # 隐藏其他
            for n, w in self.windows.items():
                if n != name:
                    w.hide()
            self.windows[name].show()
            self.config["current_character"] = name
        else:
            print(f"[Moepet] 角色 '{name}' 不存在")

    def switch_to(self, name: str):
        """切换到指定角色"""
        if name == self.config.get("current_character"):
            return  # 已经是当前角色
        self.show(name)
