"""
设置窗口 - 左导航 + 工具栏(折叠/搜索) + 右圆角卡片
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QCheckBox, QComboBox, QPushButton,
    QWidget, QListWidget, QListWidgetItem,
    QScrollArea, QFrame, QLineEdit, QSizePolicy
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve


NAV_ITEMS = [
    ("通用设置", "general", True),
    ("AI模型设置", "ai_model", False),
    ("语音合成设置", "tts", False),
    ("语音输入设置", "asr", False),
    ("角色设置", "character", True),
]

NAV_WIDTH = 150
NAV_COLLAPSED_WIDTH = 0


class SettingsWindow(QDialog):
    """设置对话框"""

    def __init__(self, config, characters: list[str], current_char: str, parent=None):
        super().__init__(parent)
        self.config = config
        self.characters = characters
        self._current_char = current_char
        self._nav_collapsed = False

        self.setWindowTitle("Moepet 设置")
        self.setMinimumSize(560, 440)
        self.resize(600, 460)

        self._setup_ui()
        self._switch_page("general")

    # ═══════════════════════════════════════════
    # 主布局
    # ═══════════════════════════════════════════

    def _setup_ui(self):
        self.setStyleSheet("QDialog { background: #f0f2f5; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ─── 工具栏行 ───
        root.addWidget(self._build_toolbar())

        # ─── 内容区（左导航 + 右内容） ───
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        self.nav_frame = self._build_left_nav()
        content.addWidget(self.nav_frame)

        self.right_area = self._build_right_area()
        content.addWidget(self.right_area, 1)

        root.addLayout(content, 1)

    # ═══════════════════════════════════════════
    # 工具栏
    # ═══════════════════════════════════════════

    def _build_toolbar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(40)
        bar.setStyleSheet("QFrame { background: #e6e9ef; border-bottom: 1px solid #d3d7de; }")

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 12, 4)
        layout.setSpacing(8)

        # 折叠按钮
        self.collapse_btn = QPushButton("☰")
        self.collapse_btn.setFixedSize(28, 28)
        self.collapse_btn.setStyleSheet("""
            QPushButton {
                background: transparent; border: none; font-size: 16px;
                color: #555; border-radius: 4px;
            }
            QPushButton:hover { background: rgba(0,0,0,0.08); }
        """)
        self.collapse_btn.clicked.connect(self._toggle_nav)
        layout.addWidget(self.collapse_btn)

        # 搜索框
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("查找设置...")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setFixedHeight(28)
        self.search_box.setStyleSheet("""
            QLineEdit {
                border: 1px solid #d3d7de; border-radius: 6px;
                padding: 2px 8px; font-size: 12px; background: #fff;
            }
            QLineEdit:focus { border-color: #3b82f6; }
        """)
        self.search_box.textChanged.connect(self._on_search)
        layout.addWidget(self.search_box, 1)

        # 搜索图标按钮（折叠后显示，初始隐藏）
        self.search_icon_btn = QPushButton("🔍")
        self.search_icon_btn.setFixedSize(28, 28)
        self.search_icon_btn.setStyleSheet("""
            QPushButton {
                background: transparent; border: none; font-size: 14px;
                border-radius: 4px;
            }
            QPushButton:hover { background: rgba(0,0,0,0.08); }
        """)
        self.search_icon_btn.clicked.connect(self._expand_search)
        self.search_icon_btn.hide()
        layout.addWidget(self.search_icon_btn)

        return bar

    # ═══════════════════════════════════════════
    # 折叠/搜索逻辑
    # ═══════════════════════════════════════════

    def _toggle_nav(self):
        self._nav_collapsed = not self._nav_collapsed

        if self._nav_collapsed:
            # 折叠：隐藏导航栏，搜索框变图标
            self.nav_frame.setFixedWidth(0)
            self.search_box.hide()
            self.search_icon_btn.show()
            self.collapse_btn.setText("▶")
        else:
            # 展开：恢复导航栏，图标变搜索框
            self.nav_frame.setFixedWidth(NAV_WIDTH)
            self.search_icon_btn.hide()
            self.search_box.show()
            self.collapse_btn.setText("☰")

    def _expand_search(self):
        """点击搜索图标时展开导航并恢复搜索框"""
        self._nav_collapsed = False
        self.nav_frame.setFixedWidth(NAV_WIDTH)
        self.search_icon_btn.hide()
        self.search_box.show()
        self.collapse_btn.setText("☰")

    def _on_search(self, text: str):
        """搜索过滤导航项"""
        for i in range(self.nav_list.count()):
            item = self.nav_list.item(i)
            label = item.text()
            visible = text.strip() == "" or text.strip().lower() in label.lower()
            item.setHidden(not visible)

    # ═══════════════════════════════════════════
    # 左侧导航
    # ═══════════════════════════════════════════

    def _build_left_nav(self) -> QWidget:
        nav_frame = QFrame()
        nav_frame.setFixedWidth(NAV_WIDTH)
        nav_frame.setStyleSheet("""
            QFrame { background: #e6e9ef; border-right: 1px solid #d3d7de; }
        """)

        layout = QVBoxLayout(nav_frame)
        layout.setContentsMargins(8, 8, 8, 16)
        layout.setSpacing(2)

        self.nav_list = QListWidget()
        self.nav_list.setStyleSheet("""
            QListWidget {
                background: transparent; border: none; outline: none;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 9px 12px; border-radius: 6px; color: #555;
            }
            QListWidget::item:selected {
                background: #ffffff; color: #3b82f6; font-weight: bold;
            }
            QListWidget::item:hover:!selected {
                background: rgba(255,255,255,0.4);
            }
        """)

        for label, key, enabled in NAV_ITEMS:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, key)
            if not enabled:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                item.setForeground(Qt.gray)
            self.nav_list.addItem(item)

        self.nav_list.setCurrentRow(0)
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        layout.addWidget(self.nav_list)
        layout.addStretch()

        return nav_frame

    # ═══════════════════════════════════════════
    # 右侧
    # ═══════════════════════════════════════════

    def _build_right_area(self) -> QWidget:
        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(20, 12, 20, 16)
        layout.setSpacing(10)

        # 右上角标题
        self.page_title = QLabel("通用设置")
        self.page_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1e293b;")
        layout.addWidget(self.page_title, alignment=Qt.AlignLeft)

        # 圆角可滚动卡片
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { width: 6px; background: transparent; border-radius: 3px; }
            QScrollBar::handle:vertical { background: #c8ccd4; border-radius: 3px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self.card = QFrame()
        self.card.setStyleSheet("QFrame { background: #ffffff; border-radius: 14px; border: 1px solid #e2e6ed; }")
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(24, 20, 24, 20)
        self.card_layout.setSpacing(14)

        scroll.setWidget(self.card)
        layout.addWidget(scroll, 1)

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        for text, slot, primary in [
            ("应用", self._on_apply, False),
            ("确定", self._on_ok, True),
            ("取消", self.reject, False),
        ]:
            btn = QPushButton(text)
            if primary:
                btn.setDefault(True)
                btn.setStyleSheet("QPushButton{background:#3b82f6;color:#fff;border:none;border-radius:7px;padding:7px 22px;font-size:13px}QPushButton:hover{background:#2563eb}")
            else:
                btn.setStyleSheet("QPushButton{background:#fff;color:#444;border:1px solid #d3d7de;border-radius:7px;padding:7px 22px;font-size:13px}QPushButton:hover{background:#f5f6fa}")
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)

        return right

    # ═══════════════════════════════════════════
    # 页面切换
    # ═══════════════════════════════════════════

    def _on_nav_changed(self, index: int):
        item = self.nav_list.item(index)
        if not item:
            return
        key = item.data(Qt.UserRole)
        self._switch_page(key)

    def _switch_page(self, key: str):
        while self.card_layout.count():
            child = self.card_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for label, k, _ in NAV_ITEMS:
            if k == key:
                self.page_title.setText(label)
                break

        {
            "general": self._build_general_page,
            "ai_model": self._build_ai_model_page,
            "tts": self._build_tts_page,
            "asr": self._build_asr_page,
            "character": self._build_character_page,
        }[key]()
        self.card_layout.addStretch()

    # ═══════════════════════════════════════════
    # 各页面
    # ═══════════════════════════════════════════

    def _build_general_page(self):
        self._section("窗口")
        self.always_top_cb = QCheckBox("始终置顶")
        self.always_top_cb.setStyleSheet("font-size:13px;")
        self.card_layout.addWidget(self.always_top_cb)

        self._section("缩放")
        row = QHBoxLayout()
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(20, 200)
        self.size_slider.setStyleSheet("QSlider::groove:horizontal{height:4px;background:#e2e6ed;border-radius:2px}QSlider::handle:horizontal{width:14px;height:14px;margin:-5px 0;background:#3b82f6;border-radius:7px}")
        self.size_label = QLabel("100%")
        self.size_label.setFixedWidth(42)
        self.size_label.setStyleSheet("color:#3b82f6;font-weight:bold;font-size:13px;")
        self.size_slider.valueChanged.connect(lambda v: self.size_label.setText(f"{v}%"))
        row.addWidget(self.size_slider, 1)
        row.addWidget(self.size_label)
        self.card_layout.addLayout(row)

        self._section("行为")
        self.click_combo = QComboBox()
        self.click_combo.addItem("切换下一张立绘", "switch_sprite")
        self.click_combo.addItem("弹跳一下", "bounce")
        self.click_combo.addItem("无反应", "none")
        self.click_combo.setStyleSheet("QComboBox{border:1px solid #d3d7de;border-radius:6px;padding:6px 10px;font-size:13px;}")
        self.card_layout.addWidget(self.click_combo)

        self.auto_idle_cb = QCheckBox("自动待机动画")
        self.auto_idle_cb.setStyleSheet("font-size:13px;")
        self.card_layout.addWidget(self.auto_idle_cb)

        self._load_general_values()

    def _load_general_values(self):
        self.always_top_cb.setChecked(self.config.get("behavior", "always_on_top", default=True))
        self.size_slider.setValue(int(self.config.get("window", "scale", default=1.0) * 100))
        action = self.config.get("behavior", "click_action", default="switch_sprite")
        idx = self.click_combo.findData(action)
        if idx >= 0:
            self.click_combo.setCurrentIndex(idx)
        self.auto_idle_cb.setChecked(self.config.get("behavior", "auto_idle", default=True))

    def _build_ai_model_page(self):
        self._placeholder("AI 对话功能将在后续版本中支持")

    def _build_tts_page(self):
        self._placeholder("语音合成（TTS）将在后续版本中支持\n音色训练计划中")

    def _build_asr_page(self):
        self._placeholder("语音输入（ASR）将在后续版本中支持")

    def _build_character_page(self):
        self._section("立绘设置")
        self.char_list = QListWidget()
        self.char_list.setStyleSheet("QListWidget{border:1px solid #e2e6ed;border-radius:8px;padding:4px;font-size:13px;max-height:120px}QListWidget::item{padding:6px 10px;border-radius:4px}QListWidget::item:selected{background:#ecf3fd;color:#3b82f6}")
        for name in self.characters:
            self.char_list.addItem(QListWidgetItem(name))
        for i in range(self.char_list.count()):
            if self.char_list.item(i).text() == self._current_char:
                self.char_list.setCurrentRow(i)
                break
        self.card_layout.addWidget(self.char_list)
        tip = QLabel("选择后点击「应用」切换角色")
        tip.setStyleSheet("color:#999;font-size:11px;")
        self.card_layout.addWidget(tip)

        self._section("接口设置")
        self._placeholder("角色 API 接口将在后续版本中支持")

    # ═══════════════════════════════════════════
    # 辅助
    # ═══════════════════════════════════════════

    def _section(self, text: str):
        label = QLabel(text)
        label.setStyleSheet("font-weight:bold;font-size:13px;color:#64748b;margin-top:2px;")
        self.card_layout.addWidget(label)

    def _placeholder(self, text: str):
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#94a3b8;font-size:13px;padding:20px;")
        lbl.setAlignment(Qt.AlignCenter)
        self.card_layout.addWidget(lbl)

    # ═══════════════════════════════════════════
    # 数据收集
    # ═══════════════════════════════════════════

    def _collect_values(self) -> dict:
        scale = getattr(self, 'size_slider', None)
        always_top = getattr(self, 'always_top_cb', None)
        click_combo = getattr(self, 'click_combo', None)
        auto_idle = getattr(self, 'auto_idle_cb', None)
        char_list = getattr(self, 'char_list', None)

        return {
            "current_character": (
                char_list.currentItem().text()
                if char_list and char_list.currentItem() else self._current_char
            ),
            "window": {"scale": scale.value() / 100.0 if scale else 1.0},
            "behavior": {
                "click_action": click_combo.currentData() if click_combo else "switch_sprite",
                "always_on_top": always_top.isChecked() if always_top else True,
                "auto_idle": auto_idle.isChecked() if auto_idle else True,
            }
        }

    def get_new_character(self) -> str | None:
        char_list = getattr(self, 'char_list', None)
        if not char_list:
            return None
        item = char_list.currentItem()
        if item and item.text() != self._current_char:
            return item.text()
        return None

    def _on_apply(self):
        values = self._collect_values()
        for key_path, update_dict in [
            (("window",), values["window"]),
            (("behavior",), values["behavior"]),
        ]:
            target = self.config.data
            for k in key_path:
                target = target.setdefault(k, {})
            target.update(update_dict)
        self.config.save()

    def _on_ok(self):
        self._on_apply()
        self.accept()
