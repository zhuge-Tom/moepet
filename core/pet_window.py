"""
桌面宠物窗口 - 透明无边框，浮动在所有窗口上方
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QLabel, QMenu, QApplication
)
from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import (
    QPixmap, QAction, QMouseEvent, QCursor
)


class PetWindow(QMainWindow):
    """透明桌面宠物窗口"""

    def __init__(self, char_dir: Path, char_config: dict, parent=None):
        super().__init__(parent)

        self.char_dir = char_dir
        self.char_config = char_config
        self.char_name = char_config.get("name", char_dir.name)
        self.sprites_dir = char_dir / "sprites"

        # 加载立绘列表
        self.sprites = self._load_sprites()

        # 当前显示的立绘索引
        self._current_sprite_index = 0

        # 拖拽相关
        self._drag_pos = QPoint()

        self._setup_window()
        self._setup_label()
        self._setup_menu()
        self._show_current_sprite()

    # ─── 初始化 ─────────────────────────────────

    def _load_sprites(self) -> list[QPixmap]:
        """从 sprites 目录加载所有立绘"""
        sprites = []
        if self.sprites_dir.exists():
            for img_path in sorted(self.sprites_dir.glob("*.png")):
                pixmap = QPixmap(str(img_path))
                if not pixmap.isNull():
                    # 按配置缩放
                    scale = self.char_config.get("scale", 1.0)
                    if scale != 1.0:
                        new_w = int(pixmap.width() * scale)
                        new_h = int(pixmap.height() * scale)
                        pixmap = pixmap.scaled(
                            new_w, new_h,
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation
                        )
                    sprites.append(pixmap)
        return sprites

    def _setup_window(self):
        """配置窗口属性"""
        self.setWindowFlags(
            Qt.FramelessWindowHint           # 无边框
            | Qt.WindowStaysOnTopHint        # 始终在最前
            | Qt.Tool                        # 不显示在任务栏
        )
        self.setAttribute(Qt.WA_TranslucentBackground)  # 透明背景
        self.setAttribute(Qt.WA_NoSystemBackground)

    def _setup_label(self):
        """设置立绘显示标签"""
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background: transparent;")
        self.setCentralWidget(self.label)

    def _setup_menu(self):
        """设置右键菜单"""
        self.menu = QMenu(self)

        # 角色切换子菜单（必须持有引用防止被 GC）
        self._switch_menu = self.menu.addMenu("切换角色")

        self.menu.addSeparator()

        # 退出
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.quit)
        self.menu.addAction(quit_action)

    def set_characters_menu(self, characters: list[str], current: str, callback):
        """设置角色切换菜单项"""
        if self._switch_menu:
            self._switch_menu.clear()
            for name in characters:
                label = f"【{'✓' if name == current else '  '}】 {name}"
                action = QAction(label, self)
                action.setData(name)
                action.triggered.connect(lambda checked, n=name: callback(n))
                self._switch_menu.addAction(action)

    # ─── 立绘切换 ─────────────────────────────

    def _show_current_sprite(self):
        """显示当前立绘"""
        if self.sprites:
            pixmap = self.sprites[self._current_sprite_index]
            self.label.setPixmap(pixmap)
            self.label.resize(pixmap.size())
            self.resize(pixmap.size())

    def next_sprite(self):
        """切换到下一张立绘（循环）"""
        if len(self.sprites) > 1:
            self._current_sprite_index = (
                (self._current_sprite_index + 1) % len(self.sprites)
            )
            self._show_current_sprite()

    def set_sprite(self, index: int):
        """切换到指定立绘"""
        if 0 <= index < len(self.sprites):
            self._current_sprite_index = index
            self._show_current_sprite()

    # ─── 交互事件 ─────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() & Qt.LeftButton and self._drag_pos is not None:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            # 如果没有拖动（点击），切换立绘
            if self._drag_pos is not None:
                delta = event.globalPosition().toPoint() - self.frameGeometry().topLeft() - self._drag_pos
                if delta.manhattanLength() < 5:  # 移动距离 < 5px 视为点击
                    self.next_sprite()
            self._drag_pos = None

    def contextMenuEvent(self, event):
        """右键菜单"""
        self.menu.exec(event.globalPos())
