"""系统托盘图标

右键菜单：显示主设置、重置立绘位置、置顶切换、退出。
"""

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QAction, QColor
from PySide6.QtCore import Signal, QObject

from core.signals import signals


class TrayIcon(QSystemTrayIcon):
    """系统托盘"""

    def __init__(self, char_name: str = "Moepet", observe_enabled: bool = False, parent=None):
        super().__init__(parent)
        self.setToolTip(f"Moepet - {char_name}")

        icon = self._make_icon()
        self.setIcon(icon)

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background: #1a1a2e;
                color: #eee;
                border: 1px solid #e94560;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background: #e94560; }
            QMenu::separator { height: 1px; background: #333; margin: 4px 8px; }
        """)

        show_action = QAction("📋 打开设置", menu)
        show_action.triggered.connect(lambda: signals.settings_changed.emit({"action": "open_settings"}))
        menu.addAction(show_action)

        reset_action = QAction("🔄 重置位置", menu)
        reset_action.triggered.connect(lambda: signals.position_changed.emit(-1, -1))
        menu.addAction(reset_action)

        dialog_action = QAction("💬 对话框", menu)
        dialog_action.triggered.connect(signals.dialog_toggle_requested.emit)
        menu.addAction(dialog_action)

        screen_action = QAction("立即识别屏幕", menu)
        screen_action.triggered.connect(
            lambda: signals.settings_changed.emit({"action": "capture_screen"}))
        menu.addAction(screen_action)

        self._observe_action = QAction("随机观察屏幕", menu)
        self._observe_action.setCheckable(True)
        self._observe_action.setChecked(observe_enabled)
        self._observe_action.toggled.connect(
            lambda enabled: signals.settings_changed.emit({
                "action": "set_screen_observation", "enabled": enabled,
            }))
        menu.addAction(self._observe_action)

        menu.addSeparator()

        quit_action = QAction("✕ 退出", menu)
        quit_action.triggered.connect(signals.quit_requested.emit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def set_observation_enabled(self, enabled: bool):
        """Reflect configuration changes without emitting another toggle action."""
        self._observe_action.blockSignals(True)
        self._observe_action.setChecked(enabled)
        self._observe_action.blockSignals(False)

    @staticmethod
    def _make_icon() -> QIcon:
        """Use the same application icon in the tray and Windows taskbar."""
        app = QApplication.instance()
        if app and not app.windowIcon().isNull():
            return app.windowIcon()
        pm = QPixmap(32, 32)
        pm.fill(QColor(0, 0, 0, 0))
        from PySide6.QtGui import QPainter, QFont
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#e94560"))
        p.setPen(QColor("#e94560"))
        p.drawEllipse(2, 2, 28, 28)
        f = QFont()
        f.setPixelSize(18)
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(pm.rect(), 0x0084, "🐱")  # AlignCenter
        p.end()
        return QIcon(pm)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            signals.settings_changed.emit({"action": "open_settings"})
