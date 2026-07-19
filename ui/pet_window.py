"""桌面宠物主窗口

透明无边框浮窗，承载立绘显示和交互。
"""

from pathlib import Path
import random

from PySide6.QtWidgets import QMainWindow, QLabel, QMenu, QApplication
from PySide6.QtCore import Qt, QPoint, QTimer, QEvent
from PySide6.QtGui import QPixmap, QAction, QMouseEvent, QCursor, QRegion

from core.signals import signals
from core.character import CharacterData
from core.animation import SpriteAnimator
from core.sprite_normalizer import common_layout, normalize_portrait


class PetWindow(QMainWindow):
    """透明桌面宠物窗口"""

    def __init__(self, char_data: CharacterData, scale_override: float = None, parent=None):
        super().__init__(parent)
        self.char_data = char_data
        self._scale = scale_override or char_data.scale
        self._current_index = 0
        self._drag_pos = QPoint()
        self._drag_start = QPoint()
        self._click_pos = QPoint()
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(220)
        self._click_timer.timeout.connect(self._handle_click_action)

        self._setup_window()
        self._setup_labels()
        self._setup_animator()
        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._next_frame)
        self._frame_state = ""
        self._frame_index = 0
        self._blink_timer = QTimer(self)
        self._blink_timer.setSingleShot(True)
        self._blink_timer.timeout.connect(self._blink)
        self._blink_restore_timer = QTimer(self)
        self._blink_restore_timer.setSingleShot(True)
        self._blink_restore_timer.timeout.connect(self._restore_blink)
        self._blink_repeat_timer = QTimer(self)
        self._blink_repeat_timer.setSingleShot(True)
        self._blink_repeat_timer.timeout.connect(self._blink)
        self._blink_repeats_left = 0
        self._current_sprite_name = ""
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._return_to_idle)
        self._click_action = "switch_sprite"
        self._auto_idle = True
        self._idle_interval_seconds = 30
        self._setup_menu()
        self._load_sprites()
        self._show_sprite()
        self.set_sprite_by_name(self.char_data.sprite_for_expression("idle"))

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
        self._animator.size_changed.connect(self._resize_to_sprite)

        # 缩放防抖：拖动滑块时不立即重绘，停下来后才应用
        self._rescale_timer = QTimer(self)
        self._rescale_timer.setSingleShot(True)
        self._rescale_timer.setInterval(120)
        self._rescale_timer.timeout.connect(self._apply_rescale)
        self._pending_scale = None

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
        source_pixmaps = [QPixmap(str(info.path)) for info in self.char_data.sprites]
        layout = common_layout(source_pixmaps)
        self._pixmaps: list[QPixmap] = []
        for pm in source_pixmaps:
            if pm.isNull():
                continue
            if layout:
                pm = normalize_portrait(pm, layout)
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
            if self.char_data.sprites:
                self._current_sprite_name = self.char_data.sprites[self._current_index].name

    def _schedule_blink(self) -> None:
        """Keep static PNG portraits alive with short, irregular eye blinks."""
        if self.char_data.blink_for_sprite(self._current_sprite_name):
            # Most blinks happen within a few seconds, with occasional longer
            # pauses so the cadence does not look mechanical.
            delay = random.randint(1100, 3300) if random.random() < 0.82 else random.randint(3600, 6200)
            self._blink_timer.start(delay)

    def _blink(self) -> None:
        closed_name = self.char_data.blink_for_sprite(self._current_sprite_name)
        closed = self._pixmap_for_name(closed_name)
        if not closed:
            self._schedule_blink()
            return
        self._blink_origin_name = self._current_sprite_name
        if self._blink_repeats_left == 0 and random.random() < 0.28:
            self._blink_repeats_left = 1
        self._label.setPixmap(closed)
        self._blink_restore_timer.start(random.randint(75, 125))

    def _restore_blink(self) -> None:
        original = self._pixmap_for_name(getattr(self, "_blink_origin_name", ""))
        if original:
            self._label.setPixmap(original)
        if self._blink_repeats_left:
            self._blink_repeats_left -= 1
            self._blink_repeat_timer.start(random.randint(120, 240))
        else:
            self._schedule_blink()

    def _resize_to_sprite(self, size):
        """Keep the transparent top-level window aligned with size animations."""
        self._label.resize(size)
        self.resize(size)
        self._overlay.setGeometry(self._label.geometry())

    def set_state(self, state: str):
        """Play configured PNG frames and fall back to the idle state."""
        cfg = self.char_data.animations.get(state) or self.char_data.animations.get("idle")
        if not cfg or not cfg.frames:
            self._frame_timer.stop()
            return
        self._blink_timer.stop()
        self._blink_restore_timer.stop()
        self._blink_repeat_timer.stop()
        self._blink_repeats_left = 0
        if state == self._frame_state and self._frame_timer.isActive():
            return
        self._frame_state, self._frame_index = state, 0
        self._frame_frames = [self._pixmap_for_name(n) for n in cfg.frames]
        self._frame_frames = [p for p in self._frame_frames if p]
        if not self._frame_frames:
            return
        if len(self._frame_frames) == 1:
            # A one-frame state is a static portrait. Do not keep a frame
            # timer alive: it would overwrite the brief closed-eye blink.
            self._frame_timer.stop()
            self._frame_state = ""
            self._current_sprite_name = Path(cfg.frames[0]).stem
            self._label.setPixmap(self._frame_frames[0])
            self._label.resize(self._frame_frames[0].size())
            self.resize(self._frame_frames[0].size())
            self._schedule_blink()
            return
        self._frame_loop = cfg.loop
        self._label.setPixmap(self._frame_frames[0])
        self._label.resize(self._frame_frames[0].size())
        self.resize(self._frame_frames[0].size())
        self._frame_timer.start(cfg.frame_ms)
        if state != "idle" and self._auto_idle:
            self._idle_timer.start(self._idle_interval_seconds * 1000)
        elif state == "idle":
            self._idle_timer.stop()

    def configure_behavior(self, click_action: str, auto_idle: bool,
                           idle_interval_seconds: int) -> None:
        """Apply interaction choices without reloading character assets."""
        self._click_action = click_action
        self._auto_idle = bool(auto_idle)
        self._idle_interval_seconds = max(5, int(idle_interval_seconds))
        if not self._auto_idle:
            self._idle_timer.stop()
        elif self._frame_state and self._frame_state != "idle":
            self._idle_timer.start(self._idle_interval_seconds * 1000)

    def _return_to_idle(self) -> None:
        if self._auto_idle:
            self.set_state("idle")

    def _pixmap_for_name(self, name: str):
        for index, info in enumerate(self.char_data.sprites):
            if info.name == Path(name).stem and index < len(self._pixmaps):
                return self._pixmaps[index]
        return None

    def _next_frame(self):
        self._frame_index += 1
        if self._frame_index >= len(self._frame_frames):
            if not self._frame_loop:
                self._frame_timer.stop()
                return
            self._frame_index = 0
        self._label.setPixmap(self._frame_frames[self._frame_index])

    # ─── 外部接口 ─────────────────────────────

    def next_sprite(self):
        """切到下一张立绘，带淡入淡出"""
        excluded = set(self.char_data.head_touch_sprite_names())
        available = [
            index for index, info in enumerate(self.char_data.sprites)
            if info.name not in excluded
        ]
        if len(available) <= 1:
            return
        try:
            current = available.index(self._current_index)
        except ValueError:
            current = -1
        self._current_index = available[(current + 1) % len(available)]
        self._animator.fade_transition(self._pixmaps[self._current_index])
        self._current_sprite_name = self.char_data.sprites[self._current_index].name
        self._schedule_blink()

    def _is_head_point(self, point: QPoint) -> bool:
        """Use the visible portrait bounds so the head hitbox follows scaling."""
        pm = self._pixmaps[self._current_index]
        bounds = QRegion(pm.mask()).boundingRect()
        if bounds.isEmpty():
            return False
        head_height = max(1, round(bounds.height() * 0.27))
        head_width = max(1, round(bounds.width() * 0.58))
        head_rect = bounds.adjusted(
            (bounds.width() - head_width) // 2,
            0,
            -(bounds.width() - head_width + 1) // 2,
            -(bounds.height() - head_height),
        )
        return head_rect.contains(point)

    def _show_head_touch_expression(self) -> bool:
        choices = [
            name for name in self.char_data.head_touch_sprite_names()
            if self._pixmap_for_name(name) is not None
        ]
        if not choices:
            return False
        self.set_sprite_by_name(random.choice(choices))
        # A touch reaction is transient; return to the normal idle portrait
        # so its regular blink cycle always resumes.
        self._idle_timer.start(2400)
        return True

    def set_sprite_by_name(self, name: str):
        """按名称切换立绘"""
        for i, info in enumerate(self.char_data.sprites):
            if info.name == name:
                # A selected expression should not be replaced by an old frame timer.
                self._frame_timer.stop()
                self._frame_state = ""
                self._blink_timer.stop()
                self._blink_restore_timer.stop()
                self._blink_repeat_timer.stop()
                self._blink_repeats_left = 0
                if i != self._current_index:
                    self._current_index = i
                    self._animator.fade_transition(self._pixmaps[i])
                else:
                    self._label.setPixmap(self._pixmaps[i])
                self._current_sprite_name = name
                self._schedule_blink()
                return

    def play_animation(self, anim_type: str):
        """播放演出动画"""
        self._animator.play(anim_type, self._label.pos(), self._label.size())

    def rescale(self, scale: float):
        """实时缩放 - 使用防抖避免拖动时残留"""
        self._pending_scale = scale
        self._rescale_timer.start()

    def _apply_rescale(self):
        """防抖结束后实际执行缩放"""
        if self._pending_scale is not None:
            self._scale = self._pending_scale
            self._pending_scale = None
            self._load_sprites()
            # Frame states cache pixmaps, so recreate the current state at the new scale.
            if self._frame_state:
                self._frame_timer.stop()
                self.set_state(self._frame_state)
            else:
                self._show_sprite()

    def set_always_on_top(self, enabled: bool):
        flags = self.windowFlags()
        if enabled:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def set_opacity(self, opacity: float):
        """Set the whole transparent pet window opacity within Qt's safe range."""
        self.setWindowOpacity(max(0.3, min(1.0, float(opacity))))

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
            QEvent.MouseButtonDblClick,
            QEvent.MouseMove,
            QEvent.MouseButtonRelease,
        ):
            if event.type() == QEvent.MouseButtonPress:
                self.mousePressEvent(event)
            elif event.type() == QEvent.MouseButtonDblClick:
                self.mouseDoubleClickEvent(event)
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
                # Delay a single click briefly so a double click can cancel it.
                self._click_pos = event.position().toPoint()
                self._click_timer.start()
            else:
                # 拖拽结束 → 记住位置
                signals.position_changed.emit(self.x(), self.y())
            self._drag_pos = QPoint()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Toggle the dialog without also treating the second click as a sprite action."""
        if event.button() == Qt.LeftButton:
            self._click_timer.stop()
            signals.dialog_toggle_requested.emit()
            event.accept()

    def _handle_click_action(self) -> None:
        if self._is_head_point(self._click_pos) and self._show_head_touch_expression():
            return
        if self._click_action == "bounce":
            self.play_animation("bounce")

    def contextMenuEvent(self, event):
        self._menu.exec(event.globalPos())
