"""宠物管理器

顶层协调者，负责角色加载、窗口管理、信号路由。
"""

from pathlib import Path

from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import Qt

from core.config import Config
from core.character import CharacterLoader, CharacterData
from core.signals import signals
from ui.pet_window import PetWindow
from ui.dialog_window import DialogWindow
from ui.settings_window import SettingsWindow
from ui.tray_icon import TrayIcon


class PetManager:
    """管理角色实例和各 UI 组件的生命周期"""

    def __init__(self, base_dir: Path, config: Config):
        self.base_dir = base_dir
        self.config = config
        self._loader = CharacterLoader(base_dir / "characters")
        self._windows: dict[str, PetWindow] = {}
        self._char_data: dict[str, CharacterData] = {}
        self._dialog: DialogWindow | None = None
        self._settings_dlg: SettingsWindow | None = None
        self._tray: TrayIcon | None = None

        self._load_characters()
        self._connect_signals()

    # ─── 初始化 ───────────────────────────────

    def _load_characters(self):
        """扫描并加载所有角色"""
        for name in self._loader.list_names():
            char_data = self._loader.load(name)
            if char_data is None:
                continue
            self._char_data[name] = char_data
            scale = self.config.get("window", "scale", default=char_data.scale)
            win = PetWindow(char_data, scale_override=scale)
            self._windows[name] = win

        # 统一注入角色菜单
        names = list(self._windows.keys())
        current = self.config.current_character
        for win in self._windows.values():
            win.set_character_menu(names, current, self._switch_character)

    def _connect_signals(self):
        """连接全局信号到处理函数"""
        signals.dialog_toggle_requested.connect(self._toggle_dialog)
        signals.sprite_change_requested.connect(self._on_sprite_request)
        signals.sprite_animation_requested.connect(self._on_anim_request)
        signals.settings_changed.connect(self._on_settings_signal)
        signals.position_changed.connect(self._on_position_changed)
        signals.quit_requested.connect(self._quit)

    def _setup_tray(self):
        """创建系统托盘"""
        current = self.config.current_character
        char = self._char_data.get(current)
        name = char.name if char else "Moepet"
        self._tray = TrayIcon(char_name=name)
        self._tray.show()

    # ─── 启动 ────────────────────────────────

    def start(self):
        """启动：显示立绘、对话框、托盘"""
        current = self.config.current_character
        if current in self._windows:
            win = self._windows[current]
            # 恢复位置
            pos = self.config.get_position("pet")
            if pos:
                win.move(*pos)
            win.show()

        self._setup_tray()

        # 如果之前对话框是打开的，恢复显示
        if self.config.get("dialog", "visible", default=False):
            self._toggle_dialog()

    # ─── 角色切换 ─────────────────────────────

    def _switch_character(self, name: str):
        if name == self.config.current_character:
            return
        old = self.config.current_character
        if old in self._windows:
            self._windows[old].hide()
        if name in self._windows:
            self._windows[name].show()
            self.config.set("current_character", name)
            self.config.save()

            # 更新菜单
            names = list(self._windows.keys())
            for win in self._windows.values():
                win.set_character_menu(names, name, self._switch_character)

            # 更新对话框角色名
            if self._dialog and self._dialog.isVisible():
                char = self._char_data.get(name)
                if char:
                    self._dialog.set_character_name(char.name)

            # 更新托盘
            if self._tray:
                char = self._char_data.get(name)
                if char:
                    self._tray.setToolTip(f"Moepet - {char.name}")

            signals.character_switched.emit(name)

    # ─── 对话框 ───────────────────────────────

    def _toggle_dialog(self):
        current = self.config.current_character
        win = self._windows.get(current)

        if self._dialog and self._dialog.isVisible():
            self._dialog.hide()
            self.config.set("dialog", "visible", False)
            self.config.save()
            return

        char = self._char_data.get(current)
        if not char:
            return

        if self._dialog is None:
            self._dialog = DialogWindow(char_name=char.name)
            self._dialog.text_submitted.connect(self._on_dialog_text)
            # 对话框初始位置在立绘旁边
            if win:
                self._dialog.move(win.x() + win.width() + 10, win.y() + 50)

        pos = self.config.get_position("dialog")
        if pos:
            self._dialog.move(*pos)

        self._dialog.show()
        self.config.set("dialog", "visible", True)
        self.config.save()

    def _on_dialog_text(self, text: str):
        """处理对话框提交的用户文本"""
        # 预留：后续接入 AI 接口
        # 暂时回显一句占位回复
        if self._dialog:
            self._dialog.display_text("（AI 对话功能即将上线~）", "assistant")

    # ─── 立绘请求 ─────────────────────────────

    def _on_sprite_request(self, name: str):
        current = self.config.current_character
        win = self._windows.get(current)
        if win:
            win.set_sprite_by_name(name)

    def _on_anim_request(self, anim_type: str):
        current = self.config.current_character
        win = self._windows.get(current)
        if win:
            win.play_animation(anim_type)

    # ─── 设置 ────────────────────────────────

    def _on_settings_signal(self, data: dict):
        if data.get("action") == "open_settings":
            self._open_settings()

    def _open_settings(self):
        if self._settings_dlg and self._settings_dlg.isVisible():
            self._settings_dlg.activateWindow()
            return

        current = self.config.current_character
        dlg = SettingsWindow(self.config, list(self._windows.keys()), current)
        dlg.setModal(False)
        dlg.setAttribute(Qt.WA_DeleteOnClose)

        dlg.scale_changed.connect(self._on_live_scale)
        dlg.apply_clicked.connect(self._apply_settings)

        def on_finished(result):
            self._settings_dlg = None
            if result == QDialog.Accepted:
                new_char = dlg.get_new_character()
                if new_char:
                    self._switch_character(new_char)
                self._apply_settings({})

        dlg.finished.connect(on_finished)
        self._settings_dlg = dlg
        dlg.show()

    def _on_live_scale(self, scale: float):
        """实时缩放反馈"""
        current = self.config.current_character
        win = self._windows.get(current)
        if win:
            win.rescale(scale)

    def _apply_settings(self, settings: dict):
        """应用设置到所有窗口"""
        always_on_top = self.config.get("window", "always_on_top", default=True)
        scale = self.config.get("window", "scale", default=0.5)

        for win in self._windows.values():
            win.set_always_on_top(always_on_top)
            win.rescale(scale)

        # 检查角色切换
        new_char = settings.get("current_character")
        if new_char and new_char != self.config.current_character:
            self._switch_character(new_char)

    # ─── 位置记忆 ─────────────────────────────

    def _on_position_changed(self, x: int, y: int):
        if x == -1 and y == -1:
            # 重置位置
            current = self.config.current_character
            win = self._windows.get(current)
            if win:
                win.move(100, 100)
                self.config.save_position("pet", 100, 100)
        else:
            self.config.save_position("pet", x, y)

    # ─── 退出 ────────────────────────────────

    def _quit(self):
        """保存状态并退出"""
        # 记住当前立绘位置
        current = self.config.current_character
        win = self._windows.get(current)
        if win:
            self.config.save_position("pet", win.x(), win.y())
        if self._dialog and self._dialog.isVisible():
            self.config.save_position("dialog", self._dialog.x(), self._dialog.y())
            self.config.set("dialog", "visible", True)
        else:
            self.config.set("dialog", "visible", False)
        self.config.save()

        if self._tray:
            self._tray.hide()
        QApplication.quit()
