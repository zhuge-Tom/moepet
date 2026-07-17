"""设置窗口

QTreeWidget 导航 + QStackedWidget 页面切换。
每个页面预构建为独立 Widget，切换时仅改 index，彻底避免重叠和闪烁。
"""

import os
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QSlider, QCheckBox, QComboBox, QPushButton,
    QScrollArea, QFrame, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QSizePolicy, QMenu, QTextEdit, QSpinBox, QStackedWidget,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal, QEvent
from PySide6.QtGui import QPainter, QFont, QIcon, QPixmap, QAction, QDesktopServices
from PySide6.QtCore import QUrl

from core.config import Config

NAV_TREE = [
    ("⚙", "通用设置", "general", True, []),
    ("🎭", "角色设置", "character", True, [
        ("🔌", "接口设置", "character_api"),
        ("🖼️", "立绘设置", "character_sprites"),
    ]),
    ("🤖", "AI 模型", "ai", True, []),
    ("🔊", "语音合成", "tts", True, []),
    ("🎤", "语音输入", "asr", True, []),
    ("📷", "屏幕识别", "screen", True, []),
    ("👁", "图像理解", "vision", True, []),
    ("ℹ", "关于", "about", True, []),
]
NAV_WIDE = 160
NAV_NARROW = 48
ANIM_MS = 220
ROW_H = 36

# 纯色替代 rgba 半透明，避免 hover 重绘闪烁
_NAV_BG = "#2c3e50"
_NAV_HOVER = "#3d5166"


class SettingsWindow(QDialog):
    scale_changed = Signal(float)
    apply_clicked = Signal(dict)

    def __init__(self, config: Config, characters: list[str], current_char: str,
                 base_dir: Path = None, parent=None):
        super().__init__(parent)
        self.config = config
        self._characters = characters
        self._current_char = current_char
        self._base_dir = base_dir or Path(__file__).parent.parent
        self._collapsed = False
        self._last_page_key = "general"
        self._anims = []

        self.setWindowTitle("Moepet 设置")
        self.setMinimumSize(580, 520)
        self.resize(760, 600)
        self.setStyleSheet("QDialog { background: #f0f2f5; }")

        self._build_ui()
        self._tree.setCurrentItem(self._tree.topLevelItem(0))

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._nav_frame = self._build_nav()
        root.addWidget(self._nav_frame)
        root.addWidget(self._build_right(), 1)

    # ═══════════════════════════════════
    # 导航栏
    # ═══════════════════════════════════

    def _build_nav(self):
        frame = QFrame()
        frame.setMinimumWidth(NAV_WIDE)
        frame.setMaximumWidth(NAV_WIDE)
        frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        frame.setStyleSheet(
            f"QFrame {{ background: {_NAV_BG}; border-right: 1px solid #1a252f; }}")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 描述行
        self._desc_row = QHBoxLayout()
        self._desc_row.setContentsMargins(6, 6, 6, 2)
        self._desc_row.setSpacing(4)
        self._desc_label = QLabel("Moepet")
        self._desc_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #ecf0f1;"
            f" background: transparent;")
        self._desc_row.addWidget(self._desc_label, 1)

        self._collapse_top = QPushButton("▶")
        self._collapse_top.setFixedSize(NAV_NARROW - 8, 24)
        self._collapse_top.setToolTip("展开导航")
        self._collapse_top.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            f" font-size: 14px; color: #bdc3c7; border-radius: 4px; }}"
            f"QPushButton:hover {{ background: {_NAV_HOVER}; }}")
        self._collapse_top.clicked.connect(self._expand_nav)
        self._collapse_top.hide()
        self._desc_row.addWidget(self._collapse_top)
        layout.addLayout(self._desc_row)

        # 折叠 + 搜索行
        self._tool_row = QHBoxLayout()
        self._tool_row.setContentsMargins(4, 2, 6, 4)
        self._tool_row.setSpacing(4)

        self._collapse_side = QPushButton("☰")
        self._collapse_side.setFixedSize(30, 28)
        self._collapse_side.setToolTip("收起导航")
        self._collapse_side.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            f" font-size: 16px; color: #bdc3c7; border-radius: 4px; }}"
            f"QPushButton:hover {{ background: {_NAV_HOVER}; }}")
        self._collapse_side.clicked.connect(self._toggle_nav)
        self._tool_row.addWidget(self._collapse_side)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("查找设置...")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setFixedHeight(28)
        self.search_box.setStyleSheet(
            "QLineEdit { border: 1px solid #34495e; border-radius: 6px;"
            " padding: 2px 6px; font-size: 11px;"
            " background: #34495e; color: #ecf0f1; }"
            "QLineEdit:focus { border-color: #e94560; }")
        self.search_box.textChanged.connect(self._on_search)
        self._tool_row.addWidget(self.search_box, 1)

        self._search_icon = QPushButton("🔍")
        self._search_icon.setFixedSize(30, 28)
        self._search_icon.setToolTip("搜索")
        self._search_icon.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            f" font-size: 13px; border-radius: 4px; }}"
            f"QPushButton:hover {{ background: {_NAV_HOVER}; }}")
        self._search_icon.clicked.connect(self._expand_nav)
        self._search_icon.hide()
        self._tool_row.addWidget(self._search_icon)
        layout.addLayout(self._tool_row)

        # 树形导航 — hover 用纯色，不用 rgba 半透明
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(16)
        self._tree.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._tree.verticalScrollBar().setEnabled(False)
        self._tree.setAnimated(True)
        self._tree.setAutoFillBackground(True)
        self._tree.setStyleSheet(f"""
            QTreeWidget {{
                background: {_NAV_BG}; border: none;
                outline: none; font-size: 13px;
            }}
            QTreeWidget::item {{
                padding: 7px 6px; border-radius: 6px; color: #bdc3c7;
            }}
            QTreeWidget::item:selected {{
                background: #e94560; color: #fff; font-weight: bold;
            }}
            QTreeWidget::item:hover:!selected {{
                background: {_NAV_HOVER};
            }}""")

        for emoji, text, key, enabled, children in NAV_TREE:
            p = QTreeWidgetItem([f" {text}"])
            p.setData(0, Qt.UserRole, key)
            p.setIcon(0, self._icon(emoji))
            if not enabled:
                p.setFlags(p.flags() & ~Qt.ItemIsEnabled)
                p.setForeground(0, Qt.gray)
            self._tree.addTopLevelItem(p)
            for ct_emoji, ct, ck in children:
                c = QTreeWidgetItem([f"{ct}"])
                c.setData(0, Qt.UserRole, ck)
                c.setIcon(0, self._icon(ct_emoji))
                p.addChild(c)
            if children:
                p.setData(0, Qt.UserRole + 1, children)

        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.currentItemChanged.connect(self._on_tree_changed)
        total_rows = sum(1 + len(ch) for _, _, _, _, ch in NAV_TREE)
        self._tree.setFixedHeight(ROW_H * total_rows + 8)
        layout.addWidget(self._tree)
        layout.addStretch()
        return frame

    @staticmethod
    def _icon(emoji):
        pm = QPixmap(20, 20)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        f = QFont()
        f.setPixelSize(16)
        p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignCenter, emoji)
        p.end()
        return QIcon(pm)

    # ═══════════════════════════════════
    # 折叠 / 展开
    # ═══════════════════════════════════

    def _toggle_nav(self):
        self._collapsed = not self._collapsed
        self._do_collapse() if self._collapsed else self._do_expand()

    def _expand_nav(self):
        if self._collapsed:
            self._collapsed = False
            self._do_expand()

    def _do_collapse(self):
        self._anim_nav_width(NAV_NARROW)
        self._desc_label.hide()
        self._collapse_top.show()
        self._desc_row.setContentsMargins(0, 2, 0, 0)
        self._collapse_side.hide()
        self.search_box.hide()
        self._search_icon.show()
        self._tool_row.setContentsMargins(0, 0, 0, 2)
        for i in range(self._tree.topLevelItemCount()):
            p = self._tree.topLevelItem(i)
            while p.childCount() > 0:
                p.removeChild(p.child(0))

    def _do_expand(self):
        self._anim_nav_width(NAV_WIDE)
        self._desc_label.show()
        self._collapse_top.hide()
        self._desc_row.setContentsMargins(6, 6, 6, 2)
        self._collapse_side.show()
        self._search_icon.hide()
        self.search_box.show()
        self._tool_row.setContentsMargins(4, 2, 6, 4)
        for i, (_, _, _, _, children) in enumerate(NAV_TREE):
            p = self._tree.topLevelItem(i)
            for ct_emoji, ct, ck in children:
                c = QTreeWidgetItem([f"{ct}"])
                c.setData(0, Qt.UserRole, ck)
                c.setIcon(0, self._icon(ct_emoji))
                p.addChild(c)

    def _anim_nav_width(self, target):
        cur = self._nav_frame.width()
        self._anims = []
        for prop in (b"minimumWidth", b"maximumWidth"):
            a = QPropertyAnimation(self._nav_frame, prop)
            a.setDuration(ANIM_MS)
            a.setStartValue(cur)
            a.setEndValue(target)
            a.setEasingCurve(QEasingCurve.InOutCubic)
            a.start()
            self._anims.append(a)

    def _on_search(self, text):
        for i in range(self._tree.topLevelItemCount()):
            p = self._tree.topLevelItem(i)
            any_vis = False
            for j in range(p.childCount()):
                c = p.child(j)
                v = not text.strip() or text.strip().lower() in c.text(0).lower()
                c.setHidden(not v)
                if v:
                    any_vis = True
            p.setHidden(not any_vis and not (
                not text.strip() or text.strip().lower() in p.text(0).lower()))

    # ═══════════════════════════════════
    # 右侧 + QStackedWidget 页面管理
    # ═══════════════════════════════════

    def _build_right(self):
        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        self._page_title = QLabel("通用设置")
        self._page_title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #1e293b;")
        layout.addWidget(self._page_title, alignment=Qt.AlignLeft)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setFocusPolicy(Qt.NoFocus)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 6px; background: transparent;"
            " border-radius: 3px; }"
            "QScrollBar::handle:vertical { background: #c8ccd4;"
            " border-radius: 3px; min-height: 30px; }"
            "QScrollBar::add-line:vertical,"
            " QScrollBar::sub-line:vertical { height: 0; }")

        # QStackedWidget: 每个页面是独立的 QWidget，切换时仅改 index
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")

        # 预构建所有页面（每个页面是独立的 Widget）
        self._pages = {}
        page_builders = [
            ("general", self._page_general),
            ("character", self._page_character_parent),
            ("character_api", self._page_character_api),
            ("character_sprites", self._page_character_sprites),
            ("ai", self._page_ai),
            ("tts", self._page_tts),
            ("asr", self._page_asr),
            ("screen", self._page_screen),
            ("vision", self._page_vision),
            ("about", self._page_about),
        ]
        for key, builder in page_builders:
            page_widget = builder()
            page_widget.setProperty("page_key", key)
            self._stack.addWidget(page_widget)
            self._pages[key] = page_widget

        scroll.setWidget(self._stack)
        layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        for text, slot, pri in [
            ("应用", self._on_apply, False),
            ("确定", self._on_ok, True),
            ("取消", self.reject, False),
        ]:
            b = QPushButton(text)
            if pri:
                b.setStyleSheet(
                    "QPushButton { background: #e94560; color: #fff;"
                    " border: none; border-radius: 7px;"
                    " padding: 7px 22px; font-size: 13px; }"
                    "QPushButton:hover { background: #ff6b6b; }")
            else:
                b.setStyleSheet(
                    "QPushButton { background: #fff; color: #444;"
                    " border: 1px solid #d3d7de; border-radius: 7px;"
                    " padding: 7px 22px; font-size: 13px; }"
                    "QPushButton:hover { background: #f5f6fa; }")
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        layout.addLayout(btn_row)
        return right

    def _switch_page(self, key):
        """QStackedWidget 切换页面 — 旧页面自动隐藏，新页面自动显示"""
        if key in self._pages:
            self._stack.setCurrentWidget(self._pages[key])
        titles = {
            "general": "通用设置", "character": "角色设置",
            "character_api": "接口设置", "character_sprites": "立绘设置",
            "ai": "AI 模型", "tts": "语音合成", "asr": "语音输入",
            "screen": "屏幕识别", "vision": "图像理解", "about": "关于",
        }
        self._page_title.setText(titles.get(key, ""))

    # ─── 页面构建工具 ─────────────────────────

    def _make_page(self):
        """创建空白页面容器，返回 (QWidget, QVBoxLayout)"""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)
        return w, lay

    def _sec(self, layout, title):
        """添加分区标题"""
        layout.addSpacing(4)
        label = QLabel(title)
        label.setStyleSheet(
            "font-weight: bold; font-size: 14px;"
            " color: #475569; margin-top: 2px;")
        layout.addWidget(label)

    def _row(self, label_text, widget, layout, stretch_label=True):
        """标签 + 控件 的水平行"""
        row = QHBoxLayout()
        row.setSpacing(16)
        lbl = QLabel(label_text)
        lbl.setStyleSheet("font-size: 13px; color: #2c3e50;")
        lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        layout.addLayout(row)
        return widget

    def _hint(self, layout, text):
        """灰色提示文字"""
        h = QLabel(text)
        h.setStyleSheet("color: #94a3b8; font-size: 11px; margin-left: 2px;")
        h.setWordWrap(True)
        layout.addWidget(h)

    def _line_edit(self, placeholder="", echo_mode=QLineEdit.Normal):
        le = QLineEdit()
        le.setPlaceholderText(placeholder)
        le.setEchoMode(echo_mode)
        le.setFixedHeight(30)
        le.setStyleSheet(
            "QLineEdit { border: 1px solid #d3d7de; border-radius: 6px;"
            " padding: 4px 10px; font-size: 13px; }"
            "QLineEdit:focus { border-color: #e94560; }")
        return le

    def _ph(self, layout, text):
        """占位提示"""
        label = QLabel(text)
        label.setStyleSheet(
            "color: #94a3b8; font-size: 13px; padding: 20px;")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

    # ═══════════════════════════════════
    # 通用设置
    # ═══════════════════════════════════

    def _page_general(self):
        page, lay = self._make_page()

        self._sec(lay, "软件设置")

        char_lbl = QLabel("角色选择")
        char_lbl.setStyleSheet("font-size: 13px; color: #2c3e50;")
        lay.addWidget(char_lbl)

        self._char_combo = QComboBox()
        self._char_combo.setFixedHeight(30)
        self._char_combo.setStyleSheet(
            "QComboBox { border: 1px solid #d3d7de; border-radius: 6px;"
            " padding: 4px 10px; font-size: 13px; }")
        for n in self._characters:
            self._char_combo.addItem(n)
        idx = self._char_combo.findText(self._current_char)
        if idx >= 0:
            self._char_combo.setCurrentIndex(idx)
        lay.addWidget(self._char_combo)

        open_folder_btn = QPushButton("📂 打开角色文件夹")
        open_folder_btn.setFixedHeight(28)
        open_folder_btn.setStyleSheet(
            "QPushButton { background: #f5f7fa; color: #444;"
            " border: 1px solid #d3d7de; border-radius: 6px;"
            " padding: 4px 12px; font-size: 12px; }"
            "QPushButton:hover { background: #e8ecf1; }")
        open_folder_btn.clicked.connect(self._open_characters_folder)
        lay.addWidget(open_folder_btn)

        self._auto_start_cb = QCheckBox("开机自启")
        self._auto_start_cb.setChecked(
            self.config.get("general", "auto_start", default=False))
        lay.addWidget(self._auto_start_cb)

        self._sec(lay, "窗口设置")

        self._always_top_cb = QCheckBox("始终置顶")
        self._always_top_cb.setChecked(
            self.config.get("window", "always_on_top", default=True))
        lay.addWidget(self._always_top_cb)

        scale_lbl = QLabel("立绘缩放")
        scale_lbl.setStyleSheet("font-size: 13px; color: #2c3e50;")
        lay.addWidget(scale_lbl)

        scale_row = QHBoxLayout()
        scale_row.setSpacing(8)
        self._scale_slider = QSlider(Qt.Horizontal)
        self._scale_slider.setRange(10, 200)
        self._scale_slider.setValue(
            int(self.config.get("window", "scale", default=0.5) * 100))
        self._scale_slider.valueChanged.connect(self._on_scale_slider)
        self._scale_slider.setFixedHeight(20)
        self._scale_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 4px;"
            " background: #e2e6ed; border-radius: 2px; }"
            "QSlider::handle:horizontal { width: 14px; height: 14px;"
            " margin: -5px 0; background: #e94560; border-radius: 7px; }"
            "QSlider::handle:horizontal:hover { background: #ff6b6b; }")
        self._scale_label = QLabel(f"{self._scale_slider.value()}%")
        self._scale_label.setFixedWidth(42)
        self._scale_label.setStyleSheet(
            "color: #e94560; font-weight: bold; font-size: 13px;")
        scale_row.addWidget(self._scale_slider, 1)
        scale_row.addWidget(self._scale_label)
        lay.addLayout(scale_row)

        _spin_qss = (
            "QSpinBox { border: 1px solid #d3d7de; border-radius: 6px;"
            " padding: 4px 8px; font-size: 13px; padding-right: 24px; }"
            "QSpinBox::up-button, QSpinBox::down-button {"
            " width: 18px; border: none; background: transparent; }"
            "QSpinBox::up-button { subcontrol-origin: border;"
            " subcontrol-position: top right; }"
            "QSpinBox::down-button { subcontrol-origin: border;"
            " subcontrol-position: bottom right; }"
            "QSpinBox::up-button:hover, QSpinBox::down-button:hover {"
            " background: #e8ecf1; }"
            "QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {"
            " background: #d3d7de; }"
            "QSpinBox::up-arrow { image: none;"
            " border-left: 4px solid transparent;"
            " border-right: 4px solid transparent;"
            " border-bottom: 5px solid #666; width: 0; height: 0; }"
            "QSpinBox::down-arrow { image: none;"
            " border-left: 4px solid transparent;"
            " border-right: 4px solid transparent;"
            " border-top: 5px solid #666; width: 0; height: 0; }"
        )

        self._typing_speed = QSpinBox()
        self._typing_speed.setRange(10, 500)
        self._typing_speed.setValue(
            self.config.get("general", "typing_speed", default=40))
        self._typing_speed.setSuffix(" ms/字")
        self._typing_speed.setFixedHeight(30)
        self._typing_speed.setMinimumWidth(120)
        self._typing_speed.setStyleSheet(_spin_qss)
        self._typing_speed.setToolTip("每个字显示的间隔；数值越小越快。")
        self._row("逐字显示速度", self._typing_speed, lay)

        self._dialog_scale = QSpinBox()
        self._dialog_scale.setRange(50, 200)
        self._dialog_scale.setValue(
            self.config.get("general", "dialog_scale", default=100))
        self._dialog_scale.setSuffix(" %")
        self._dialog_scale.setFixedHeight(30)
        self._dialog_scale.setMinimumWidth(120)
        self._dialog_scale.setStyleSheet(_spin_qss)
        self._dialog_scale.setToolTip("应用后立即调整对话框大小和控件字体。")
        self._row("对话框缩放", self._dialog_scale, lay)

        self._sec(lay, "行为")

        self._click_combo = QComboBox()
        self._click_combo.addItem("切换下一张立绘", "switch_sprite")
        self._click_combo.addItem("弹跳动画", "bounce")
        self._click_combo.addItem("无反应", "none")
        self._click_combo.setFixedHeight(30)
        self._click_combo.setStyleSheet(
            "QComboBox { border: 1px solid #d3d7de; border-radius: 6px;"
            " padding: 6px 10px; font-size: 13px; }")
        current = self.config.get("behavior", "click_action",
                                  default="switch_sprite")
        idx = self._click_combo.findData(current)
        if idx >= 0:
            self._click_combo.setCurrentIndex(idx)
        self._row("点击立绘", self._click_combo, lay)

        self._auto_idle_cb = QCheckBox("自动待机动画")
        self._auto_idle_cb.setChecked(
            self.config.get("behavior", "auto_idle", default=True))
        lay.addWidget(self._auto_idle_cb)

        lay.addStretch()
        return page

    def _open_characters_folder(self):
        folder = self._base_dir / "characters"
        if folder.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ═══════════════════════════════════
    # 角色设置 > 接口设置
    # ═══════════════════════════════════

    def _page_character_api(self):
        page, lay = self._make_page()

        self._sec(lay, "对话设置")

        prompt_lbl = QLabel("角色提示词（system prompt）")
        prompt_lbl.setStyleSheet(
            "font-size: 13px; color: #2c3e50; font-weight: bold;")
        lay.addWidget(prompt_lbl)

        self._system_prompt = QTextEdit()
        self._system_prompt.setPlaceholderText(
            "设定角色的性格、说话方式、回复格式...")
        self._system_prompt.setFixedHeight(120)
        self._system_prompt.setPlainText(
            self.config.get("character_prompt", "system_prompt", default=""))
        self._system_prompt.setStyleSheet(
            "QTextEdit { border: 1px solid #d3d7de; border-radius: 8px;"
            " padding: 8px; font-size: 13px; }"
            "QTextEdit:focus { border-color: #e94560; }")
        lay.addWidget(self._system_prompt)

        self._hint(lay, "提示词决定了角色的性格和回复风格")

        lay.addSpacing(8)
        self._sec(lay, "格式提示词（可选）")

        self._format_prompt = QTextEdit()
        self._format_prompt.setPlaceholderText(
            "例如：每句话前加上心情标签，格式为 {心情}|{回复}")
        self._format_prompt.setFixedHeight(80)
        self._format_prompt.setPlainText(
            self.config.get("character_prompt", "format_prompt", default=""))
        self._format_prompt.setStyleSheet(
            "QTextEdit { border: 1px solid #d3d7de; border-radius: 8px;"
            " padding: 8px; font-size: 13px; }"
            "QTextEdit:focus { border-color: #e94560; }")
        lay.addWidget(self._format_prompt)

        lay.addStretch()
        return page

    # ═══════════════════════════════════
    # 角色设置 > 立绘设置
    # ═══════════════════════════════════

    def _page_character_sprites(self):
        page, lay = self._make_page()

        self._sec(lay, "当前角色立绘")

        self._sprite_list = QTreeWidget()
        self._sprite_list.setHeaderHidden(True)
        self._sprite_list.setStyleSheet(
            "QTreeWidget { border: 1px solid #e2e6ed; border-radius: 8px;"
            " padding: 4px; font-size: 13px; }"
            "QTreeWidget::item { padding: 6px 10px; border-radius: 4px; }"
            "QTreeWidget::item:selected {"
            " background: #fce4ec; color: #e94560; }")
        self._sprite_list.setFixedHeight(140)
        lay.addWidget(self._sprite_list)

        # 首次填充
        self._refresh_sprite_list()

        row = QHBoxLayout()
        row.addStretch()
        open_sprite_btn = QPushButton("📂 打开立绘文件夹")
        open_sprite_btn.setStyleSheet(
            "QPushButton { background: #f5f7fa; color: #444;"
            " border: 1px solid #d3d7de; border-radius: 6px;"
            " padding: 4px 12px; font-size: 12px; }"
            "QPushButton:hover { background: #e8ecf1; }")
        open_sprite_btn.clicked.connect(self._open_sprites_folder)
        row.addWidget(open_sprite_btn)
        lay.addLayout(row)

        self._hint(lay, "将 .png 立绘文件放入 sprites 文件夹即可自动加载")

        lay.addStretch()
        return page

    def _refresh_sprite_list(self):
        """刷新立绘列表（切换角色时调用）"""
        self._sprite_list.clear()
        char_dir = self._base_dir / "characters" / self._current_char / "sprites"
        if char_dir.exists():
            for img in sorted(char_dir.glob("*.png")):
                item = QTreeWidgetItem(
                    [f"🖼️  {img.stem}  ({img.stat().st_size // 1024}KB)"])
                item.setData(0, Qt.UserRole, str(img))
                self._sprite_list.addTopLevelItem(item)

    def _open_sprites_folder(self):
        char_dir = self._base_dir / "characters" / self._current_char / "sprites"
        if char_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(char_dir)))

    # ═══════════════════════════════════
    # AI 模型
    # ═══════════════════════════════════

    def _page_ai(self):
        page, lay = self._make_page()

        self._sec(lay, "OpenAI 兼容 API")

        self._ai_url = self._line_edit("https://api.deepseek.com/v1")
        self._ai_url.setText(self.config.get("llm", "base_url", default=""))
        self._row("Base URL", self._ai_url, lay)

        self._hint(lay, "支持 DeepSeek / OpenAI / 本地 Ollama 等"
                        " OpenAI 兼容接口")

        self._ai_key = self._line_edit("sk-xxxx", QLineEdit.Password)
        self._ai_key.setText(self.config.get("llm", "api_key", default=""))
        self._row("API Key", self._ai_key, lay)

        self._ai_model = self._line_edit(
            "deepseek-chat / gpt-4o-mini / ...")
        self._ai_model.setText(self.config.get("llm", "model", default=""))
        self._row("Model", self._ai_model, lay)

        self._sec(lay, "高级设定")

        self._ai_stream_cb = QCheckBox("启用流式输出（逐字显示）")
        self._ai_stream_cb.setChecked(
            self.config.get("llm", "stream", default=True))
        lay.addWidget(self._ai_stream_cb)

        self._ai_post = self._line_edit("例如 <think>.*?</think>")
        self._ai_post.setText(
            self.config.get("llm", "post_processing", default=""))
        self._row("回复后处理（正则）", self._ai_post, lay)

        self._hint(lay, "用正则表达式删除回复中不需要的部分，如模型思考过程")

        self._ai_ignore_err_cb = QCheckBox("忽略格式错误")
        self._ai_ignore_err_cb.setChecked(
            self.config.get("llm", "ignore_format_error", default=True))
        lay.addWidget(self._ai_ignore_err_cb)

        lay.addSpacing(4)
        test_btn = QPushButton("🔗 测试连接")
        test_btn.setFixedHeight(32)
        test_btn.setStyleSheet(
            "QPushButton { background: #3498db; color: #fff;"
            " border: none; border-radius: 7px;"
            " padding: 7px 22px; font-size: 13px; }"
            "QPushButton:hover { background: #2980b9; }")
        test_btn.clicked.connect(self._test_connection)
        lay.addWidget(test_btn)

        self._test_status = QLabel("")
        self._test_status.setWordWrap(True)
        self._test_status.setStyleSheet("font-size: 12px; padding: 4px;")
        lay.addWidget(self._test_status)

        lay.addStretch()
        return page

    def _test_connection(self):
        """测试 API 连接"""
        from core.llm_service import LLMService
        self._test_status.setText("连接中...")
        self._test_status.setStyleSheet(
            "color: #3498db; font-size: 12px; padding: 4px;")

        self._test_llm = LLMService(self)
        self._test_llm.configure(
            self._ai_url.text().strip(),
            self._ai_key.text().strip(),
            self._ai_model.text().strip(),
        )
        self._test_llm.set_system_prompt("回复一个字：好")
        self._test_llm.add_user_message("测试")
        self._test_llm.response_finished.connect(self._on_test_success)
        self._test_llm.error_occurred.connect(self._on_test_error)
        self._test_llm.send(stream=False)

    def _on_test_success(self, text):
        self._test_status.setText("✅ 连接成功！")
        self._test_status.setStyleSheet(
            "color: #27ae60; font-size: 12px; padding: 4px;")

    def _on_test_error(self, err):
        self._test_status.setText(f"❌ {err}")
        self._test_status.setStyleSheet(
            "color: #e74c3c; font-size: 12px; padding: 4px;")

    # ═══════════════════════════════════
    # TTS / ASR / 关于
    # ═══════════════════════════════════

    def _page_character_parent(self):
        page, lay = self._make_page()
        self._ph(lay, "请在下方选择「接口设置」或「立绘设置」")
        lay.addStretch()
        return page

    def _page_tts(self):
        page, lay = self._make_page()
        self._sec(lay, "本地 CosyVoice 音色克隆")
        self._tts_enabled = QCheckBox("LLM 回复后自动朗读")
        self._tts_enabled.setChecked(self.config.get("tts", "enabled", default=False))
        lay.addWidget(self._tts_enabled)
        self._tts_model = self._line_edit("用户下载的 CosyVoice 模型目录")
        self._tts_model.setText(self.config.get("tts", "model_path", default=""))
        self._row("模型目录", self._tts_model, lay)
        self._tts_speed = QSpinBox()
        self._tts_speed.setRange(50, 200)
        self._tts_speed.setSuffix("%")
        self._tts_speed.setValue(int(self.config.get("tts", "speed", default=1.0) * 100))
        self._row("语速", self._tts_speed, lay)
        self._hint(lay, "在角色 voice/ 中放置本人或已获授权的 10–60 秒参考音频。")
        lay.addStretch()
        return page

    def _page_asr(self):
        page, lay = self._make_page()
        self._sec(lay, "本地 faster-whisper")
        self._asr_enabled = QCheckBox("启用按键语音输入")
        self._asr_enabled.setChecked(self.config.get("asr", "enabled", default=False))
        lay.addWidget(self._asr_enabled)
        self._asr_model = self._line_edit("用户下载的 faster-whisper 模型目录")
        self._asr_model.setText(self.config.get("asr", "model_path", default=""))
        self._row("模型目录", self._asr_model, lay)
        self._asr_hotkey = self._line_edit("Ctrl+Alt+Space")
        self._asr_hotkey.setText(self.config.get("asr", "hotkey", default="Ctrl+Alt+Space"))
        self._row("按住说话快捷键", self._asr_hotkey, lay)
        self._hint(lay, "首次接入需安装可选语音依赖；未配置模型时不会录音。")
        lay.addStretch()
        return page

    def _page_screen(self):
        page, lay = self._make_page()
        self._sec(lay, "主动截图 OCR")
        self._screen_keep = QCheckBox("保留截图（默认识别后删除）")
        self._screen_keep.setChecked(self.config.get("screen_capture", "keep_captures", default=False))
        lay.addWidget(self._screen_keep)
        self._screen_hotkey = self._line_edit("Ctrl+Alt+O")
        self._screen_hotkey.setText(self.config.get("screen_capture", "hotkey", default="Ctrl+Alt+O"))
        self._row("截图快捷键", self._screen_hotkey, lay)
        self._screen_cloud_first = QCheckBox("优先使用已配置的云端视觉模型，失败时本地 OCR")
        self._screen_cloud_first.setChecked(self.config.get("screen_capture", "cloud_first", default=True))
        lay.addWidget(self._screen_cloud_first)
        self._hint(lay, "在聊天中说“识别屏幕/看屏幕”或按快捷键即可截图；不会后台监控。")
        lay.addStretch()
        return page

    def _page_vision(self):
        page, lay = self._make_page()
        self._sec(lay, "可选图像理解")
        self._vision_enabled = QCheckBox("允许主动发送截图到已配置的视觉服务")
        self._vision_enabled.setChecked(self.config.get("vision", "enabled", default=False))
        lay.addWidget(self._vision_enabled)
        self._vision_url = self._line_edit("本地 Ollama 或云端 OpenAI 兼容地址")
        self._vision_url.setText(self.config.get("vision", "base_url", default=""))
        self._row("Base URL", self._vision_url, lay)
        self._vision_model = self._line_edit("视觉模型名称")
        self._vision_model.setText(self.config.get("vision", "model", default=""))
        self._row("模型", self._vision_model, lay)
        self._vision_key = self._line_edit("可选 API Key", QLineEdit.Password)
        self._row("API Key", self._vision_key, lay)
        self._hint(lay, "只有你明确选择图像理解时才会发送截图；本地服务可不填 Key。")
        lay.addStretch()
        return page

    def _page_about(self):
        page, lay = self._make_page()
        about = QLabel(
            "Moepet - 萌系桌面宠物\n"
            "基于 PySide6 的桌面宠物应用\n\n"
            "支持多角色切换、AI 对话、Galgame 风格对话框、\n"
            "立绘动画演出、系统托盘等功能。\n\n"
            "GitHub: zhuge-Tom/moepet")
        about.setStyleSheet("color: #555; font-size: 13px; padding: 16px;")
        about.setAlignment(Qt.AlignCenter)
        lay.addWidget(about)
        lay.addStretch()
        return page

    # ═══════════════════════════════════
    # 导航事件
    # ═══════════════════════════════════

    def _on_tree_changed(self, cur, prev):
        if not cur:
            return
        children = cur.data(0, Qt.UserRole + 1)
        if children:
            return
        self._switch_page(cur.data(0, Qt.UserRole))

    def _on_item_clicked(self, item, col):
        # Keep navigation selection in sync before routing the page.  This also
        # guarantees the QTreeWidget selected style is visible after a click.
        self._tree.setCurrentItem(item)
        children = item.data(0, Qt.UserRole + 1)
        if children:
            if self._collapsed:
                # 折叠状态：弹菜单选择子页面
                self._popup_children_menu(item, children)
                # 恢复到上一个选中的非父节点
                if self._last_page_key:
                    for i in range(self._tree.topLevelItemCount()):
                        p = self._tree.topLevelItem(i)
                        if p.data(0, Qt.UserRole) == self._last_page_key:
                            self._tree.setCurrentItem(p)
                            break
                        for j in range(p.childCount()):
                            c = p.child(j)
                            if c.data(0, Qt.UserRole) == self._last_page_key:
                                self._tree.setCurrentItem(c)
                                break
            else:
                # 展开状态：切换子项的展开/收起
                item.setExpanded(not item.isExpanded())
        else:
            self._last_page_key = item.data(0, Qt.UserRole)
            self._switch_page(self._last_page_key)

    def _popup_children_menu(self, item, children):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #2c3e50; color: #ecf0f1;
                    border: 1px solid #e94560;
                    border-radius: 6px; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background: #e94560; }""")
        for emoji, text, key in children:
            action = QAction(f"{emoji}  {text}", self)
            action.setData(key)
            action.triggered.connect(
                lambda checked, k=key: self._on_child_selected(k))
            menu.addAction(action)
        rect = self._tree.visualItemRect(item)
        pos = self._tree.viewport().mapToGlobal(rect.bottomLeft())
        menu.exec(pos)

    def _on_child_selected(self, key):
        """子菜单选中后：切换页面 + 更新导航高亮"""
        self._last_page_key = key
        self._switch_page(key)
        # 在树中高亮对应的子项
        for i in range(self._tree.topLevelItemCount()):
            p = self._tree.topLevelItem(i)
            for j in range(p.childCount()):
                c = p.child(j)
                if c.data(0, Qt.UserRole) == key:
                    self._tree.setCurrentItem(c)
                    return

    # ═══════════════════════════════════
    # 配置收集
    # ═══════════════════════════════════

    def _collect_settings(self) -> dict:
        import shiboken6 as sb

        def safe(obj, default=None):
            if obj is None:
                return default
            try:
                if not sb.isValid(obj):
                    return default
            except Exception:
                return default
            return obj

        s = {}

        # 通用
        s["current_character"] = (
            safe(getattr(self, "_char_combo", None),
                 type("", (), {"currentText": lambda: self._current_char})()
                 ).currentText()
            if safe(getattr(self, "_char_combo", None))
            else self._current_char
        )
        s["window"] = {
            "scale": (
                safe(getattr(self, "_scale_slider", None),
                     type("", (), {"value": lambda: 50})()
                     ).value() / 100.0
                if safe(getattr(self, "_scale_slider", None))
                else self.config.get("window", "scale", default=0.5)
            ),
            "always_on_top": (
                safe(getattr(self, "_always_top_cb", None),
                     type("", (), {"isChecked": lambda: True})()
                     ).isChecked()
                if safe(getattr(self, "_always_top_cb", None))
                else True
            ),
        }
        s["behavior"] = {
            "click_action": (
                safe(getattr(self, "_click_combo", None),
                     type("", (), {"currentData": lambda: "switch_sprite"})()
                     ).currentData()
                if safe(getattr(self, "_click_combo", None))
                else "switch_sprite"
            ),
            "auto_idle": (
                safe(getattr(self, "_auto_idle_cb", None),
                     type("", (), {"isChecked": lambda: True})()
                     ).isChecked()
                if safe(getattr(self, "_auto_idle_cb", None))
                else True
            ),
        }
        s["general"] = {
            "typing_speed": (
                safe(getattr(self, "_typing_speed", None),
                     type("", (), {"value": lambda: 40})()
                     ).value()
                if safe(getattr(self, "_typing_speed", None))
                else 40
            ),
            "dialog_scale": (
                safe(getattr(self, "_dialog_scale", None),
                     type("", (), {"value": lambda: 100})()
                     ).value()
                if safe(getattr(self, "_dialog_scale", None))
                else 100
            ),
            "auto_start": (
                safe(getattr(self, "_auto_start_cb", None),
                     type("", (), {"isChecked": lambda: False})()
                     ).isChecked()
                if safe(getattr(self, "_auto_start_cb", None))
                else False
            ),
        }

        # AI
        ai_url = safe(getattr(self, "_ai_url", None))
        ai_key = safe(getattr(self, "_ai_key", None))
        ai_model = safe(getattr(self, "_ai_model", None))
        ai_stream = safe(getattr(self, "_ai_stream_cb", None))
        ai_post = safe(getattr(self, "_ai_post", None))
        ai_ignore = safe(getattr(self, "_ai_ignore_err_cb", None))
        if ai_url or ai_key or ai_model:
            s["llm"] = {
                "base_url": ai_url.text().strip() if ai_url else "",
                "api_key": ai_key.text().strip() if ai_key else "",
                "model": ai_model.text().strip() if ai_model else "",
                "stream": ai_stream.isChecked() if ai_stream else True,
                "post_processing": (
                    ai_post.text().strip() if ai_post else ""),
                "ignore_format_error": (
                    ai_ignore.isChecked() if ai_ignore else True),
            }

        # 角色提示词
        sys_prompt = safe(getattr(self, "_system_prompt", None))
        fmt_prompt = safe(getattr(self, "_format_prompt", None))
        if sys_prompt or fmt_prompt:
            s["character_prompt"] = {
                "system_prompt": (
                    sys_prompt.toPlainText() if sys_prompt else ""),
                "format_prompt": (
                    fmt_prompt.toPlainText() if fmt_prompt else ""),
            }

        s["tts"] = {"enabled": safe(getattr(self, "_tts_enabled", None)).isChecked() if safe(getattr(self, "_tts_enabled", None)) else False,
                    "model_path": safe(getattr(self, "_tts_model", None)).text().strip() if safe(getattr(self, "_tts_model", None)) else "",
                    "speed": safe(getattr(self, "_tts_speed", None)).value() / 100.0 if safe(getattr(self, "_tts_speed", None)) else 1.0}
        s["asr"] = {"enabled": safe(getattr(self, "_asr_enabled", None)).isChecked() if safe(getattr(self, "_asr_enabled", None)) else False,
                    "model_path": safe(getattr(self, "_asr_model", None)).text().strip() if safe(getattr(self, "_asr_model", None)) else "",
                    "hotkey": safe(getattr(self, "_asr_hotkey", None)).text().strip() if safe(getattr(self, "_asr_hotkey", None)) else "Ctrl+Alt+Space"}
        s["screen_capture"] = {"keep_captures": safe(getattr(self, "_screen_keep", None)).isChecked() if safe(getattr(self, "_screen_keep", None)) else False,
                               "hotkey": safe(getattr(self, "_screen_hotkey", None)).text().strip() if safe(getattr(self, "_screen_hotkey", None)) else "Ctrl+Alt+O",
                               "cloud_first": safe(getattr(self, "_screen_cloud_first", None)).isChecked() if safe(getattr(self, "_screen_cloud_first", None)) else True}
        s["vision"] = {"enabled": safe(getattr(self, "_vision_enabled", None)).isChecked() if safe(getattr(self, "_vision_enabled", None)) else False,
                       "base_url": safe(getattr(self, "_vision_url", None)).text().strip() if safe(getattr(self, "_vision_url", None)) else "",
                       "model": safe(getattr(self, "_vision_model", None)).text().strip() if safe(getattr(self, "_vision_model", None)) else "",
                       "api_key": safe(getattr(self, "_vision_key", None)).text().strip() if safe(getattr(self, "_vision_key", None)) else ""}

        return s

    def get_new_character(self) -> str | None:
        cl = getattr(self, "_char_combo", None)
        if not cl:
            return None
        return (
            cl.currentText()
            if cl.currentText() != self._current_char
            else None
        )

    def _on_apply(self):
        v = self._collect_settings()
        # API keys are written to the platform keyring, never config.json.
        for section in ("llm", "vision"):
            key = v.get(section, {}).pop("api_key", "")
            if key:
                self.config.set_secret(section, key)
        for section, data in v.items():
            if isinstance(data, dict):
                for k, val in data.items():
                    self.config.set(section, k, val)
            else:
                self.config.set(section, data)
        self.config.save()
        self.apply_clicked.emit(v)

    def _on_scale_slider(self, v):
        self._scale_label.setText(f"{v}%")
        self.scale_changed.emit(v / 100.0)

    def _on_ok(self):
        self._on_apply()
        self.accept()
