"""设置窗口

左侧导航 + 右侧卡片式页面，支持折叠。
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QSlider, QCheckBox, QComboBox, QPushButton,
    QScrollArea, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal

from core.config import Config
from ui.theme import SETTINGS_QSS

NAV_ITEMS = [
    ("⚙", "通用设置", "general"),
    ("🎭", "角色设置", "character"),
    ("🤖", "AI 模型", "ai"),
    ("🔊", "语音合成", "tts"),
    ("🎤", "语音输入", "asr"),
    ("ℹ", "关于", "about"),
]
NAV_WIDE = 160
NAV_NARROW = 48
ANIM_MS = 200


class SettingsWindow(QDialog):
    """设置主窗口"""

    scale_changed = Signal(float)
    apply_clicked = Signal(dict)

    def __init__(self, config: Config, characters: list[str], current_char: str, parent=None):
        super().__init__(parent)
        self.config = config
        self._characters = characters
        self._current_char = current_char
        self._collapsed = False

        self.setWindowTitle("Moepet 设置")
        self.setMinimumSize(520, 440)
        self.resize(640, 500)
        self.setStyleSheet(SETTINGS_QSS)

        self._build_ui()
        self._switch_page("general")

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 左侧导航
        self._nav = self._build_nav()
        root.addWidget(self._nav)

        # 右侧内容
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(24, 16, 24, 16)
        right_layout.setSpacing(12)

        self._page_title = QLabel("通用设置")
        self._page_title.setObjectName("page_title")
        right_layout.addWidget(self._page_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }"
                             "QScrollBar:vertical { width: 5px; background: transparent; }"
                             "QScrollBar::handle:vertical { background: #ccc; border-radius: 2px; }")

        self._card = QFrame()
        self._card.setObjectName("card")
        self._card_layout = QVBoxLayout(self._card)
        self._card_layout.setContentsMargins(24, 20, 24, 20)
        self._card_layout.setSpacing(14)

        scroll.setWidget(self._card)
        right_layout.addWidget(scroll, 1)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        apply_btn = QPushButton("应用")
        apply_btn.setObjectName("secondary_btn")
        apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(apply_btn)

        ok_btn = QPushButton("确定")
        ok_btn.setObjectName("primary_btn")
        ok_btn.clicked.connect(self._on_ok)
        btn_row.addWidget(ok_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondary_btn")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        right_layout.addLayout(btn_row)
        root.addWidget(right, 1)

    # ─── 导航栏 ───────────────────────────────

    def _build_nav(self) -> QFrame:
        nav = QFrame()
        nav.setObjectName("nav_panel")
        nav.setMinimumWidth(NAV_WIDE)
        nav.setMaximumWidth(NAV_WIDE)
        nav.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        layout = QVBoxLayout(nav)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(2)

        # 标题
        self._nav_title = QLabel("Moepet")
        self._nav_title.setStyleSheet("color: white; font-size: 16px; font-weight: bold; padding: 8px;")
        layout.addWidget(self._nav_title)

        # 折叠按钮
        self._toggle_btn = QPushButton("☰")
        self._toggle_btn.setStyleSheet("""
            QPushButton { background: transparent; color: white; font-size: 18px;
                          border: none; padding: 8px; border-radius: 4px; }
            QPushButton:hover { background: rgba(255,255,255,0.15); }
        """)
        self._toggle_btn.clicked.connect(self._toggle_collapse)
        layout.addWidget(self._toggle_btn)

        layout.addSpacing(8)

        # 导航按钮
        self._nav_buttons: dict[str, QPushButton] = {}
        for emoji, text, key in NAV_ITEMS:
            btn = QPushButton(f"{emoji}  {text}")
            btn.setProperty("page_key", key)
            btn.clicked.connect(lambda checked, k=key: self._switch_page(k))
            layout.addWidget(btn)
            self._nav_buttons[key] = btn

        layout.addStretch()

        return nav

    def _toggle_collapse(self):
        self._collapsed = not self._collapsed
        target = NAV_NARROW if self._collapsed else NAV_WIDE

        anim = QPropertyAnimation(self._nav, b"minimumWidth")
        anim.setDuration(ANIM_MS)
        anim.setStartValue(self._nav.width())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.InOutCubic)
        anim.start()

        anim2 = QPropertyAnimation(self._nav, b"maximumWidth")
        anim2.setDuration(ANIM_MS)
        anim2.setStartValue(self._nav.width())
        anim2.setEndValue(target)
        anim2.setEasingCurve(QEasingCurve.InOutCubic)
        anim2.start()

        # 保存引用防止 GC
        self._nav_anims = [anim, anim2]

        self._nav_title.setVisible(not self._collapsed)
        for btn in self._nav_buttons.values():
            btn.setText(btn.text().split("  ")[-1] if self._collapsed else
                        f"{NAV_ITEMS[[k for k, _ in self._nav_buttons.items()].index(btn.property('page_key'))][0]}  {btn.text()}" if self._collapsed else "")

    # ─── 页面切换 ─────────────────────────────

    def _switch_page(self, key: str):
        # 清空卡片
        while self._card_layout.count():
            item = self._card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 更新导航高亮
        for k, btn in self._nav_buttons.items():
            btn.setProperty("active", "true" if k == key else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        # 找到标题
        for emoji, text, k in NAV_ITEMS:
            if k == key:
                self._page_title.setText(text)
                break

        # 渲染页面
        pages = {
            "general": self._page_general,
            "character": self._page_character,
            "ai": self._page_ai,
            "tts": self._page_tts,
            "asr": self._page_asr,
            "about": self._page_about,
        }
        pages.get(key, self._page_general)()
        self._card_layout.addStretch()

    def _section(self, title: str):
        label = QLabel(title)
        label.setObjectName("section_title")
        self._card_layout.addWidget(label)

    def _placeholder(self, text: str):
        label = QLabel(text)
        label.setStyleSheet("color: #94a3b8; font-size: 13px; padding: 20px;")
        label.setAlignment(Qt.AlignCenter)
        self._card_layout.addWidget(label)

    # ─── 页面实现 ─────────────────────────────

    def _page_general(self):
        self._section("窗口")

        self._always_top_cb = QCheckBox("始终置顶")
        self._always_top_cb.setChecked(self.config.get("window", "always_on_top", default=True))
        self._card_layout.addWidget(self._always_top_cb)

        self._section("缩放")
        row = QHBoxLayout()
        self._scale_slider = QSlider(Qt.Horizontal)
        self._scale_slider.setRange(10, 200)
        self._scale_slider.setValue(int(self.config.get("window", "scale", default=0.5) * 100))
        self._scale_slider.valueChanged.connect(self._on_scale_change)

        self._scale_label = QLabel(f"{self._scale_slider.value()}%")
        self._scale_label.setStyleSheet("color: #e94560; font-weight: bold; font-size: 13px;")
        self._scale_label.setFixedWidth(48)

        row.addWidget(self._scale_slider, 1)
        row.addWidget(self._scale_label)
        self._card_layout.addLayout(row)

        self._section("行为")

        self._click_combo = QComboBox()
        self._click_combo.addItem("切换下一张立绘", "switch_sprite")
        self._click_combo.addItem("弹跳动画", "bounce")
        self._click_combo.addItem("无反应", "none")
        current = self.config.get("behavior", "click_action", default="switch_sprite")
        idx = self._click_combo.findData(current)
        if idx >= 0:
            self._click_combo.setCurrentIndex(idx)
        self._card_layout.addWidget(self._click_combo)

        self._auto_idle_cb = QCheckBox("自动待机动画")
        self._auto_idle_cb.setChecked(self.config.get("behavior", "auto_idle", default=True))
        self._card_layout.addWidget(self._auto_idle_cb)

    def _page_character(self):
        self._section("当前角色")
        self._char_combo = QComboBox()
        for name in self._characters:
            self._char_combo.addItem(name)
        idx = self._char_combo.findText(self._current_char)
        if idx >= 0:
            self._char_combo.setCurrentIndex(idx)
        self._card_layout.addWidget(self._char_combo)

        hint = QLabel("选择后点击「应用」切换角色")
        hint.setStyleSheet("color: #999; font-size: 11px;")
        self._card_layout.addWidget(hint)

        self._section("立绘设置")
        self._placeholder("立绘管理功能将在后续版本中支持")

    def _page_ai(self):
        self._placeholder("AI 对话功能将在后续版本中支持")

    def _page_tts(self):
        self._placeholder("语音合成（TTS）将在后续版本中支持\n音色训练计划中")

    def _page_asr(self):
        self._placeholder("语音输入（ASR）将在后续版本中支持")

    def _page_about(self):
        about_text = QLabel(
            "Moepet - 萌系桌面宠物\n"
            "基于 PySide6 的桌面宠物应用\n\n"
            "支持多角色切换、Galgame 风格对话框、\n"
            "立绘动画演出、系统托盘等功能。\n\n"
            "GitHub: zhuge-Tom/moepet"
        )
        about_text.setStyleSheet("color: #555; font-size: 13px; padding: 16px; line-height: 1.6;")
        about_text.setAlignment(Qt.AlignCenter)
        self._card_layout.addWidget(about_text)

    # ─── 配置收集 ─────────────────────────────

    def _collect_settings(self) -> dict:
        s = {
            "window": {
                "scale": self._scale_slider.value() / 100.0,
                "always_on_top": self._always_top_cb.isChecked(),
            },
            "behavior": {
                "click_action": self._click_combo.currentData(),
                "auto_idle": self._auto_idle_cb.isChecked(),
            },
        }
        char = self._char_combo.currentText()
        if char != self._current_char:
            s["current_character"] = char
        return s

    def _on_scale_change(self, value: int):
        self._scale_label.setText(f"{value}%")
        self.scale_changed.emit(value / 100.0)

    def _on_apply(self):
        settings = self._collect_settings()
        # 写入 config
        for section, data in settings.items():
            if isinstance(data, dict):
                for k, v in data.items():
                    self.config.set(section, k, v)
            else:
                self.config.set(section, data)
        self.config.save()
        self.apply_clicked.emit(settings)

    def _on_ok(self):
        self._on_apply()
        self.accept()

    def get_new_character(self) -> str | None:
        char = self._char_combo.currentText()
        return char if char != self._current_char else None
