"""桌面宠物主窗口

透明无边框浮窗，承载立绘显示和交互。
"""

from pathlib import Path

from PySide6.QtWidgets import QMainWindow, QLabel, QMenu, QApplication
from PySide6.QtCore import Qt, QPoint, QTimer, QEvent
from PySide6.QtGui import QPixmap, QAction, QMouseEvent, QCursor

from core.signals import signals
from core.character import CharacterData
from core.animation import SpriteAnimator


class PetWindow(QMainWindow):
    """透明桌面宠物窗口"""

    def __init__(self, char_data: CharacterData, scale_override: float = None, parent=None):
        super().__init__(parent)
        self.char_data = char_data
        self._scale = scale_override or char_data.scale
        self._current_index = 0
        self._drag_pos = QPoint()
        self._drag_start = QPoint()

        self._setup_window()
        self._setup_labels()
        self._setup_animator()
        self._setup_menu()
        self._load_sprites()
        self._show_sprite()

    # ─── 初始化 ───────────────────────────────

    def _setup_window(self):
        flags = (
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def _setup_labels(self):
        """主标签 + 淡出用的覆盖标签"""
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet("background: transparent;")
        self._label.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._label.installEventFilter(self)
        self.setCentralWidget(self._label)

        # 用于淡出过渡的第二层标签
        self._overlay = QLabel(self)
        self._overlay.setAlignment(Qt.AlignCenter)
        self._overlay.setStyleSheet("background: transparent;")
        self._overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._overlay.hide()

    def _setup_animator(self):
        self._animator = SpriteAnimator(self, self._label, self._overlay)

    def _setup_menu(self):
        self._menu = QMenu(self)
        self._menu.setStyleSheet("""
            QMenu {
                background: #1a1a2e;
                color: #eee;
                border: 1px solid #e94560;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: #e94560;
            }
            QMenu::separator {
                height: 1px;
                background: #333;
                margin: 4px 8px;
            }
        """)

        self._switch_menu = self._menu.addMenu("切换角色")
        self._menu.addSeparator()

        dialog_action = QAction("💬 对话框", self)
        dialog_action.triggered.connect(signals.dialog_toggle_requested.emit)
        self._menu.addAction(dialog_action)

        settings_action = QAction("⚙ 设置", self)
        settings_action.triggered.connect(self._open_settings)
        self._menu.addAction(settings_action)

        self._menu.addSeparator()

        quit_action = QAction("✕ 退出", self)
        quit_action.triggered.connect(signals.quit_requested.emit)
        self._menu.addAction(quit_action)

    def _open_settings(self):
        """通过信号通知管理器打开设置"""
        from core.signals import signals
        signals.settings_changed.emit({"action": "open_settings"})

    def _load_sprites(self):
        """从角色目录加载所有立绘"""
        self._pixmaps: list[QPixmap] = []
        for sprite_info in self.char_data.sprites:
            pm = QPixmap(str(sprite_info.path))
            if pm.isNull():
                continue
            if self._scale != 1.0:
                w = int(pm.width() * self._scale)
                h = int(pm.height() * self._scale)
                pm = pm.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._pixmaps.append(pm)

        if not self._pixmaps:
            # 没有立绘时显示占位
            pm = QPixmap(200, 300)
            pm.fill(Qt.transparent)
            self._pixmaps.append(pm)

        self._current_index = min(self._current_index, len(self._pixmaps) - 1)

    def _show_sprite(self):
        if self._pixmaps:
            pm = self._pixmaps[self._current_index]
            self._label.setPixmap(pm)
            self._label.resize(pm.size())
            self.resize(pm.size())

    # ─── 外部接口 ─────────────────────────────

    def next_sprite(self):
        """切到下一张立绘，带淡入淡出"""
        if len(self._pixmaps) <= 1:
            return
        self._current_index = (self._current_index + 1) % len(self._pixmaps)
        self._animator.fade_transition(self._pixmaps[self._current_index])

    def set_sprite_by_name(self, name: str):
        """按名称切换立绘"""
        for i, info in enumerate(self.char_data.sprites):
            if info.name == name:
                if i != self._current_index:
                    self._current_index = i
                    self._animator.fade_transition(self._pixmaps[i])
                return

    def play_animation(self, anim_type: str):
        """播放演出动画"""
        self._animator.play(anim_type, self._label.pos(), self._label.size())

    def rescale(self, scale: float):
        """实时缩放"""
        self._scale = scale
        self._load_sprites()
        self._show_sprite()

    def set_always_on_top(self, enabled: bool):
        flags = self.windowFlags()
        if enabled:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def set_character_menu(self, names: list[str], current: str, callback):
        """更新角色切换子菜单"""
        self._switch_menu.clear()
        for name in names:
            mark = "✓" if name == current else " "
            action = QAction(f"【{mark}】{name}", self)
            action.setData(name)
            action.triggered.connect(lambda checked, n=name: callback(n))
            self._switch_menu.addAction(action)

    # ─── 事件处理 ─────────────────────────────

    def eventFilter(self, obj, event):
        """把 label 的鼠标事件转发给窗口"""
        if obj is self._label and event.type() in (
            QEvent.MouseButtonPress,
            QEvent.MouseMove,
            QEvent.MouseButtonRelease,
        ):
            if event.type() == QEvent.MouseButtonPress:
                self.mousePressEvent(event)
            elif event.type() == QEvent.MouseMove:
                self.mouseMoveEvent(event)
            elif event.type() == QEvent.MouseButtonRelease:
                self.mouseReleaseEvent(event)
            return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._drag_start = event.globalPosition().toPoint()
            event.accept()
        elif event.button() == Qt.RightButton:
            # 右键显示对话框
            signals.dialog_toggle_requested.emit()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() & Qt.LeftButton and self._drag_pos:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            end_pos = event.globalPosition().toPoint()
            delta = end_pos - self._drag_start
            if delta.manhattanLength() < 5:
                # 点击 → 切换立绘
                self.next_sprite()
            else:
                # 拖拽结束 → 记住位置
                signals.position_changed.emit(self.x(), self.y())
            self._drag_pos = QPoint()

    def contextMenuEvent(self, event):
        self._menu.exec(event.globalPos())
