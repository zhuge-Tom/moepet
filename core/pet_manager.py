"""
角色管理器 - 负责加载、切换角色
"""

import json
from pathlib import Path

from PySide6.QtWidgets import QDialog
from PySide6.QtCore import Qt

from core.config import Config
from core.pet_window import PetWindow
from core.settings_window import SettingsWindow


class PetManager:
    """管理所有角色实例"""

    def __init__(self, characters_dir: Path, config: Config):
        self.characters_dir = characters_dir
        self.config = config
        self.windows: dict[str, PetWindow] = {}
        self._init_characters()

    def _init_characters(self):
        """扫描所有角色目录"""
        if not self.characters_dir.exists():
            return

        # 先创建所有窗口
        for char_dir in sorted(self.characters_dir.iterdir()):
            if char_dir.is_dir():
                char_config_path = char_dir / "config.json"
                if char_config_path.exists():
                    with open(char_config_path, "r", encoding="utf-8") as f:
                        char_cfg = json.load(f)
                    self.windows[char_dir.name] = PetWindow(char_dir, char_cfg)

        # 统一注入菜单
        char_names = list(self.windows.keys())
        current = self.config.current_character
        for name, window in self.windows.items():
            window.set_characters_menu(char_names, current, self.switch_to)
            window.set_settings_callback(self._open_settings)

    # ─── 角色管理 ─────────────────────────────

    def show_current(self):
        """显示当前角色"""
        current = self.config.current_character
        if current in self.windows:
            self.windows[current].show()
        else:
            print(f"[Moepet] 角色 '{current}' 未找到，可用角色: {list(self.windows.keys())}")

    def show(self, name: str):
        """显示指定角色"""
        if name in self.windows:
            for n, w in self.windows.items():
                if n != name:
                    w.hide()
            self.windows[name].show()
            self.config.data["current_character"] = name
            self.config.save()
        else:
            print(f"[Moepet] 角色 '{name}' 不存在")

    def switch_to(self, name: str):
        """切换到指定角色"""
        if name == self.config.current_character:
            return
        self.show(name)

    # ─── 设置窗口 ─────────────────────────────

    def _open_settings(self):
        """打开设置窗口（非模态，不阻塞桌宠交互）"""
        char_names = list(self.windows.keys())
        current = self.config.current_character

        # 如果已有设置窗口打开，激活它
        if hasattr(self, '_settings_dlg') and self._settings_dlg and self._settings_dlg.isVisible():
            self._settings_dlg.activateWindow()
            return

        dlg = SettingsWindow(self.config, char_names, current)
        dlg.setModal(False)
        dlg.setAttribute(Qt.WA_DeleteOnClose)

        # 实时缩放反馈
        dlg.scale_changed.connect(self._on_scale_changed)
        # 应用按钮
        dlg.apply_clicked.connect(self._apply_settings)

        def on_finished(result):
            self._settings_dlg = None
            if result == QDialog.Accepted:
                new_char = dlg.get_new_character()
                if new_char and new_char != current:
                    self.switch_to(new_char)
                    self._update_menus()
                self._apply_settings()

        dlg.finished.connect(on_finished)
        self._settings_dlg = dlg
        dlg.show()

    def _update_menus(self):
        """更新所有窗口的角色切换菜单"""
        char_names = list(self.windows.keys())
        current = self.config.current_character
        for name, window in self.windows.items():
            window.set_characters_menu(char_names, current, self.switch_to)

    def _apply_settings(self):
        """应用设置到所有窗口"""
        always_on_top = self.config.get("behavior", "always_on_top", default=True)
        scale = self.config.get("window", "scale", default=1.0)

        for window in self.windows.values():
            # 更新置顶状态
            flags = window.windowFlags()
            if always_on_top:
                flags |= Qt.WindowStaysOnTopHint
            else:
                flags &= ~Qt.WindowStaysOnTopHint
            window.setWindowFlags(flags)
            window.show()
            # 应用缩放
            window.rescale(scale)

    def _on_scale_changed(self, scale: float):
        """实时缩放立绘"""
        current = self.config.current_character
        if current in self.windows:
            self.windows[current].rescale(scale)
