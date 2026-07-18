"""设置窗口

QTreeWidget 导航 + QStackedWidget 页面切换。
每个页面预构建为独立 Widget，切换时仅改 index，彻底避免重叠和闪烁。
"""

import json
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
from PySide6.QtWidgets import QFileDialog, QMessageBox
from core.knowledge_base import KnowledgeBase
from core.openai_compat import chat_completions_url, is_local_endpoint
from ui.settings_components import IntegrationOverview
from ui.settings.probes import (
    ModelDiscoveryRunner, ProbeRunner, probe_cosyvoice, probe_http_endpoint, probe_local_module,
    probe_ocr,
)
from ui.settings.service_status import (
    asr_ready, llm_ready, observation_ready, tts_ready, vision_connection_ready,
    vision_ready,
)
from ui.settings.persistence import apply_settings, save_character_prompt
from ui.settings.pages import (
    make_about_page, make_asr_page, make_character_parent_page, make_screen_page,
    make_tts_page, make_vision_page, make_ai_page,
)
from ui.settings.provider_presets import (
    CHAT_PRESETS, VISION_PRESETS, preset_by_key, preset_key_for_url,
)

from core.config import Config

NAV_TREE = [
    ("⚙", "通用设置", "general", True, []),
    ("🎭", "角色设置", "character", True, [
        ("🔌", "接口设置", "character_api"),
        ("🖼️", "立绘设置", "character_sprites"),
        ("📚", "角色资料库", "character_knowledge"),
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
        self._probe_widgets = {}
        self._probe_runner = ProbeRunner(self)
        self._model_runner = ModelDiscoveryRunner(self)
        self._settings_baseline = ""

        self.setWindowTitle("Moepet 设置")
        self.setMinimumSize(580, 520)
        self.resize(760, 600)
        self.setStyleSheet("""
            QDialog { background: #f4f6f9; }
            QCheckBox { color: #334155; spacing: 8px; font-size: 13px; }
            QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid #cbd5e1; border-radius: 4px; background: #fff; }
            QCheckBox::indicator:checked { background: #e94560; border-color: #e94560; }
            QComboBox { background: #fff; color: #1e293b; }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox QAbstractItemView {
                background: #ffffff; color: #1e293b;
                border: 1px solid #cbd5e1; outline: none;
                selection-background-color: #fce7ec; selection-color: #9f1239;
            }
            QComboBox QAbstractItemView::item { min-height: 28px; padding: 4px 8px; }
            QComboBox QAbstractItemView::item:hover { background: #f8fafc; color: #1e293b; }
        """)

        self._build_ui()
        self._probe_runner.finished.connect(self._on_probe_finished)
        self._model_runner.finished.connect(self._on_models_discovered)
        self._tree.setCurrentItem(self._tree.topLevelItem(0))
        self._settings_baseline = self._settings_snapshot()
        self._watch_settings_changes()
        self._refresh_dirty_state()

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
        layout.setContentsMargins(28, 20, 28, 0)
        layout.setSpacing(10)

        self._page_title = QLabel("通用设置")
        self._page_title.setStyleSheet(
            "font-size: 21px; font-weight: bold; color: #172033;")
        layout.addWidget(self._page_title, alignment=Qt.AlignLeft)

        self._page_description = QLabel()
        self._page_description.setWordWrap(True)
        self._page_description.setStyleSheet(
            "font-size: 12px; color: #64748b; margin-bottom: 4px;")
        layout.addWidget(self._page_description)

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
        content_card = QFrame()
        content_card.setObjectName("settings_content_card")
        content_card.setStyleSheet(
            "QFrame#settings_content_card { background: #ffffff;"
            " border: 1px solid #e2e8f0; border-radius: 12px; }")
        card_layout = QVBoxLayout(content_card)
        card_layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")

        # 预构建所有页面（每个页面是独立的 Widget）
        self._pages = {}
        page_builders = [
            ("general", self._page_general),
            ("character", make_character_parent_page),
            ("character_api", self._page_character_api),
            ("character_sprites", self._page_character_sprites),
            ("character_knowledge", self._page_character_knowledge),
            ("ai", self._build_ai_page),
            ("tts", self._build_tts_page),
            ("asr", self._build_asr_page),
            ("screen", self._build_screen_page),
            ("vision", self._build_vision_page),
            ("about", make_about_page),
        ]
        for key, builder in page_builders:
            page_widget = builder()
            page_widget.setProperty("page_key", key)
            self._stack.addWidget(page_widget)
            self._pages[key] = page_widget

        # Combo popups are separate Qt windows on some Windows themes, so the
        # dialog stylesheet alone does not reliably reach their item views.
        for combo in self._stack.findChildren(QComboBox):
            combo.view().setStyleSheet("""
                QAbstractItemView {
                    background: #ffffff;
                    color: #1e293b;
                    border: 1px solid #cbd5e1;
                    selection-background-color: #fce7ec;
                    selection-color: #9f1239;
                    outline: none;
                }
                QAbstractItemView::item {
                    min-height: 28px;
                    padding: 4px 8px;
                }
                QAbstractItemView::item:hover {
                    background: #f8fafc;
                    color: #1e293b;
                }
            """)

        scroll.setWidget(self._stack)
        card_layout.addWidget(scroll)
        layout.addWidget(content_card, 1)

        footer = QFrame()
        footer.setStyleSheet("QFrame { border-top: 1px solid #e2e8f0; background: #ffffff; }")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 12, 0, 14)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._dirty_label = QLabel()
        self._dirty_label.setStyleSheet("color: #b45309; font-size: 12px; font-weight: 600;")
        footer_layout.addWidget(self._dirty_label)
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
        footer_layout.addLayout(btn_row)
        layout.addWidget(footer)
        return right

    def _watch_settings_changes(self) -> None:
        """Track edits centrally so closing a long configuration form is safe."""
        for field in self._stack.findChildren(QLineEdit):
            field.textChanged.connect(self._refresh_dirty_state)
        for field in self._stack.findChildren(QTextEdit):
            field.textChanged.connect(self._refresh_dirty_state)
        for field in self._stack.findChildren(QCheckBox):
            field.stateChanged.connect(self._refresh_dirty_state)
        for field in self._stack.findChildren(QComboBox):
            field.currentIndexChanged.connect(self._refresh_dirty_state)
        for field in self._stack.findChildren(QSpinBox):
            field.valueChanged.connect(self._refresh_dirty_state)
        for field in self._stack.findChildren(QSlider):
            field.valueChanged.connect(self._refresh_dirty_state)

    def _settings_snapshot(self) -> str:
        prompts = {
            "system": self._system_prompt.toPlainText() if hasattr(self, "_system_prompt") else "",
            "format": self._format_prompt.toPlainText() if hasattr(self, "_format_prompt") else "",
        }
        return json.dumps({"settings": self._collect_settings(), "prompts": prompts},
                          ensure_ascii=False, sort_keys=True)

    def _has_unsaved_changes(self) -> bool:
        return bool(self._settings_baseline and self._settings_snapshot() != self._settings_baseline)

    def _refresh_dirty_state(self, *_args) -> None:
        if hasattr(self, "_dirty_label"):
            self._dirty_label.setText("有未保存的更改" if self._has_unsaved_changes() else "")

    def reject(self) -> None:
        if self._has_unsaved_changes():
            answer = QMessageBox.question(
                self, "放弃未保存的更改？", "当前页面有未保存的设置，确定放弃吗？",
                QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel,
            )
            if answer != QMessageBox.Discard:
                return
        super().reject()

    def _switch_page(self, key):
        """QStackedWidget 切换页面 — 旧页面自动隐藏，新页面自动显示"""
        if key in self._pages:
            self._stack.setCurrentWidget(self._pages[key])
        titles = {
            "general": "通用设置", "character": "角色设置",
            "character_api": "接口设置", "character_sprites": "立绘设置",
            "character_knowledge": "角色资料库",
            "ai": "AI 模型", "tts": "语音合成", "asr": "语音输入",
            "screen": "屏幕识别", "vision": "图像理解", "about": "关于",
        }
        self._page_title.setText(titles.get(key, ""))
        descriptions = {
            "general": "调整桌宠的显示、交互和日常行为。",
            "character": "从左侧子项管理角色的连接、立绘与资料。",
            "character_api": "配置当前角色的对话服务与提示词。",
            "character_sprites": "管理当前角色使用的立绘和动画资源。",
            "character_knowledge": "导入和维护角色在对话中参考的资料。",
            "ai": "选择模型服务，并填写连接所需的信息。",
            "tts": "配置回复朗读所使用的语音服务。",
            "asr": "配置语音输入与本地识别选项。",
            "screen": "按需启用屏幕识别，并设置快捷键和隐私选项。",
            "vision": "配置截图后交给模型理解的方式。",
            "about": "查看版本信息、项目说明和相关链接。",
        }
        self._page_description.setText(descriptions.get(key, ""))

    # ─── 页面构建工具 ─────────────────────────

    def _make_page(self):
        """创建空白页面容器，返回 (QWidget, QVBoxLayout)"""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(28, 24, 28, 28)
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
        return label

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
        h.setMinimumHeight(32)
        h.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addWidget(h)
        return h

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

    def _add_probe_row(self, layout, key, text, prepare_probe):
        row = QHBoxLayout()
        button = QPushButton(text)
        button.setFixedHeight(30)
        button.setStyleSheet(
            "QPushButton { background: #eef2ff; color: #3730a3;"
            " border: 1px solid #c7d2fe; border-radius: 6px; padding: 4px 14px; }"
            "QPushButton:hover { background: #e0e7ff; }")
        status = QLabel("尚未测试")
        status.setWordWrap(True)
        status.setStyleSheet("color: #64748b; font-size: 12px;")
        row.addWidget(button)
        row.addWidget(status, 1)
        layout.addLayout(row)
        self._probe_widgets[key] = (button, status)
        button.clicked.connect(lambda: self._start_probe(key, prepare_probe))

    def _start_probe(self, key, prepare_probe):
        button, status = self._probe_widgets[key]
        button.setEnabled(False)
        status.setText("正在后台测试...")
        status.setStyleSheet("color: #2563eb; font-size: 12px;")
        try:
            probe = prepare_probe()
        except Exception as exc:
            self._on_probe_finished(
                key, False, f"无法准备测试：{type(exc).__name__}: {str(exc)[:120]}")
            return
        self._probe_runner.run(key, probe)

    def _on_probe_finished(self, key, ok, message):
        pair = self._probe_widgets.get(key)
        if pair is None:
            return
        button, status = pair
        button.setEnabled(True)
        status.setText(message)
        status.setStyleSheet(
            f"color: {'#15803d' if ok else '#dc2626'}; font-size: 12px;")

    def _discover_models(self, key: str, url_field, key_field, picker, status) -> None:
        """Request provider models in the background and keep the manual model editable."""
        button = getattr(self, f"_{key}_discover_button")
        button.setEnabled(False)
        status.setText("正在后台获取模型列表...")
        status.setStyleSheet("color: #2563eb; font-size: 12px;")
        self._model_requests = getattr(self, "_model_requests", {})
        self._model_requests[key] = (button, picker, status)
        self._model_runner.run(key, url_field.text().strip(), key_field.text().strip())

    def _on_models_discovered(self, key: str, ok: bool, message: str, models: list) -> None:
        request = getattr(self, "_model_requests", {}).pop(key, None)
        if request is None:
            return
        button, picker, status = request
        button.setEnabled(True)
        status.setText(message)
        status.setStyleSheet(
            f"color: {'#15803d' if ok else '#dc2626'}; font-size: 12px;")
        if not ok:
            return
        picker.blockSignals(True)
        picker.clear()
        picker.addItems(models)
        picker.blockSignals(False)
        picker.setVisible(True)
        if key in ("tts", "asr"):
            provider = getattr(self, f"_{key}_provider")
            picker.setVisible(provider.currentData() == "cloud")

    def _apply_provider_preset(self, preset_key: str, presets, url_field, model_field) -> None:
        """Fill known endpoints as a shortcut; custom values stay fully editable."""
        preset = preset_by_key(preset_key, presets)
        if preset.key == "custom":
            return
        url_field.setText(preset.base_url)
        if not model_field.text().strip() or preset_key != "custom":
            model_field.setText(preset.default_model)

    def _sync_preset_from_url(self, base_url: str, preset_box, presets) -> None:
        target = preset_box.findData(preset_key_for_url(base_url, presets))
        preset_box.blockSignals(True)
        preset_box.setCurrentIndex(max(target, 0))
        preset_box.blockSignals(False)

    def _prepare_asr_probe(self):
        provider = self._asr_provider.currentData()
        model_path = self._asr_model.text().strip()
        url = self._asr_api_url.text().strip()
        key = self._asr_api_key.text().strip()
        model = self._asr_api_model.text().strip() or "whisper-1"
        if provider == "cloud":
            return lambda: probe_http_endpoint(url, key, {"model": model})
        return lambda: probe_local_module("faster_whisper", model_path)

    def _prepare_tts_probe(self):
        model_path = self._tts_model.text().strip()
        provider = self._tts_provider.currentData()
        url = self._tts_api_url.text().strip()
        key = self._tts_api_key.text().strip()
        if provider == "gpt_sovits_remote":
            if url and not url.rstrip("/").endswith("/tts"):
                url = url.rstrip("/") + "/tts"
            return lambda: probe_http_endpoint(url, key, {})
        return lambda: probe_cosyvoice(model_path)

    def _prepare_ocr_probe(self):
        return probe_ocr

    def _prepare_vision_probe(self):
        base_url = chat_completions_url(self._vision_url.text().strip())
        api_key = self._vision_key.text().strip()
        model = self._vision_model.text().strip()
        if not base_url:
            return lambda: (False, "请先填写视觉服务地址")
        if not model:
            return lambda: (False, "请先填写视觉模型名称")
        tiny_png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        payload = {
            "model": model,
            "max_tokens": 8,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": "Reply OK."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{tiny_png}"}},
            ]}],
        }
        return lambda: probe_http_endpoint(base_url, api_key, payload)

    def _build_screen_page(self):
        page, fields = make_screen_page(
            self.config,
            lambda layout, key, text: self._add_probe_row(
                layout, key, text, self._prepare_ocr_probe),
        )
        for name, widget in fields.items():
            setattr(self, f"_{name}", widget)
        return page

    def _build_vision_page(self):
        page, fields = make_vision_page(
            self.config,
            lambda layout, key, text: self._add_probe_row(
                layout, key, text, self._prepare_vision_probe),
        )
        for name, widget in fields.items():
            setattr(self, f"_{name}", widget)
        self._vision_discover_button.clicked.connect(
            lambda: self._discover_models(
                "vision", self._vision_url, self._vision_key,
                self._vision_model_picker, self._vision_discover_status))
        self._vision_model_picker.activated.connect(
            lambda _index: self._vision_model.setText(self._vision_model_picker.currentText()))
        self._vision_provider_preset.currentIndexChanged.connect(
            lambda _index: self._apply_provider_preset(
                self._vision_provider_preset.currentData(), VISION_PRESETS,
                self._vision_url, self._vision_model))
        self._vision_url.textEdited.connect(
            lambda text: self._sync_preset_from_url(
                text, self._vision_provider_preset, VISION_PRESETS))
        self._vision_enabled.stateChanged.connect(self._refresh_service_status_cards)
        self._vision_allow_cloud.stateChanged.connect(self._refresh_service_status_cards)
        for field in (self._vision_url, self._vision_model, self._vision_key):
            field.textChanged.connect(self._refresh_service_status_cards)
        return page

    def _build_tts_page(self):
        page, fields, rows = make_tts_page(
            self.config,
            lambda layout, key, text: self._add_probe_row(
                layout, key, text, self._prepare_tts_probe),
        )
        for name, widget in fields.items():
            setattr(self, f"_{name}", widget)
        self._tts_rows = rows
        self._tts_local_fields = (self._tts_model, self._tts_local_url, self._tts_local_config)
        self._tts_cloud_fields = (self._tts_api_url, self._tts_api_key, self._tts_remote_reference)
        self._tts_provider.currentIndexChanged.connect(self._sync_tts_provider_fields)
        self._tts_discover_button.setVisible(False)
        self._tts_model_picker.setVisible(False)
        self._tts_discover_status.setVisible(False)
        self._tts_enabled.stateChanged.connect(self._refresh_service_status_cards)
        for field in (self._tts_model, self._tts_local_url, self._tts_local_config,
                      self._tts_api_url, self._tts_api_key, self._tts_remote_reference):
            field.textChanged.connect(self._refresh_service_status_cards)
        self._sync_tts_provider_fields()
        return page

    def _build_asr_page(self):
        page, fields, rows = make_asr_page(
            self.config,
            lambda layout, key, text: self._add_probe_row(
                layout, key, text, self._prepare_asr_probe),
        )
        for name, widget in fields.items():
            setattr(self, f"_{name}", widget)
        self._asr_rows = rows
        self._asr_local_fields = (
            self._asr_engine, self._asr_model, self._asr_device, self._asr_compute,
        )
        self._asr_cloud_fields = (
            self._asr_api_url, self._asr_api_key, self._asr_api_model, self._asr_api_language,
        )
        self._asr_provider.currentIndexChanged.connect(self._sync_asr_provider_fields)
        self._asr_discover_button.clicked.connect(
            lambda: self._discover_models(
                "asr", self._asr_api_url, self._asr_api_key,
                self._asr_model_picker, self._asr_discover_status))
        self._asr_model_picker.activated.connect(
            lambda _index: self._asr_api_model.setText(self._asr_model_picker.currentText()))
        self._asr_enabled.stateChanged.connect(self._refresh_service_status_cards)
        for field in (self._asr_model, self._asr_api_url, self._asr_api_key,
                      self._asr_api_model):
            field.textChanged.connect(self._refresh_service_status_cards)
        self._sync_asr_provider_fields()
        return page

    def _build_ai_page(self):
        page, fields = make_ai_page(self.config)
        for name, widget in fields.items():
            setattr(self, f"_{name}", widget)
        self._ai_test_button.clicked.connect(self._test_connection)
        self._ai_discover_button.clicked.connect(
            lambda: self._discover_models(
                "ai", self._ai_url, self._ai_key,
                self._ai_model_picker, self._ai_discover_status))
        self._ai_model_picker.activated.connect(
            lambda _index: self._ai_model.setText(self._ai_model_picker.currentText()))
        self._ai_provider_preset.currentIndexChanged.connect(
            lambda _index: self._apply_provider_preset(
                self._ai_provider_preset.currentData(), CHAT_PRESETS,
                self._ai_url, self._ai_model))
        self._ai_url.textEdited.connect(
            lambda text: self._sync_preset_from_url(
                text, self._ai_provider_preset, CHAT_PRESETS))
        for field in (self._ai_url, self._ai_key, self._ai_model):
            field.textChanged.connect(self._refresh_service_status_cards)
        self._refresh_service_status_cards()
        return page

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

        llm_is_ready = llm_ready(self.config)
        tts_is_ready = tts_ready(self.config)
        asr_is_ready = asr_ready(self.config)
        vision_is_ready = vision_ready(self.config)
        observe_is_ready = observation_ready(self.config)
        overview = IntegrationOverview("Moepet 控制中心", [
            ("1. 角色对话", "连接你的 OpenAI 兼容聊天模型。", llm_is_ready, "ai"),
            ("2. 语音朗读", "为角色回复选择本地或云端 TTS。", tts_is_ready, "tts"),
            ("3. 按住说话", "按住快捷键录音，松开后自动转写。", asr_is_ready, "asr"),
            ("4. 识图与观察", "手动识图，或在明确授权后随机观察屏幕。", observe_is_ready, "screen"),
        ], self._open_page)
        lay.addWidget(overview)

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

        self._opacity = QSpinBox()
        self._opacity.setRange(30, 100)
        self._opacity.setSuffix(" %")
        self._opacity.setValue(
            int(self.config.get("window", "opacity", default=1.0) * 100))
        self._opacity.setFixedHeight(30)
        self._row("桌宠透明度", self._opacity, lay)

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

        self._idle_interval = QSpinBox()
        self._idle_interval.setRange(5, 600)
        self._idle_interval.setSuffix(" 秒")
        self._idle_interval.setValue(
            self.config.get("behavior", "idle_interval", default=30))
        self._idle_interval.setFixedHeight(30)
        self._idle_interval.setStyleSheet(_spin_qss)
        self._row("恢复待机时间", self._idle_interval, lay)

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
        prompt = self._character_prompt()
        self._system_prompt.setPlainText(prompt.get("system_prompt", ""))
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
        self._format_prompt.setPlainText(prompt.get("format_prompt", ""))
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

    def _page_character_knowledge(self):
        page, lay = self._make_page()
        self._sec(lay, "世界观、角色设定与对话示例")
        self._knowledge_enabled = QCheckBox("聊天时自动检索并使用导入资料")
        self._knowledge_enabled.setChecked(self.config.get("knowledge", "enabled", default=True))
        lay.addWidget(self._knowledge_enabled)
        self._knowledge_status = QLabel()
        self._knowledge_status.setWordWrap(True)
        self._knowledge_status.setStyleSheet("color: #64748b; font-size: 12px;")
        lay.addWidget(self._knowledge_status)
        self._knowledge_type = QComboBox()
        self._knowledge_type.addItem("世界观 / 背景", "world")
        self._knowledge_type.addItem("角色设定", "character")
        self._knowledge_type.addItem("对话示例", "dialogue")
        self._knowledge_type.setStyleSheet("""
            QComboBox { background: #ffffff; color: #2c3e50;
                        border: 1px solid #d3d7de; border-radius: 6px;
                        padding: 4px 10px; min-height: 20px; }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox QAbstractItemView { background: #ffffff; color: #2c3e50;
                                          border: 1px solid #d3d7de;
                                          selection-background-color: #fce4ec;
                                          selection-color: #e94560;
                                          outline: none; }
            QComboBox QAbstractItemView::item { min-height: 26px; padding: 4px 8px; }
            QComboBox QAbstractItemView::item:hover { background: #f5f7fa; }
        """)
        self._row("导入资料类型", self._knowledge_type, lay)
        import_btn = QPushButton("导入资料文件（TXT / Markdown / JSON）")
        import_btn.setFixedHeight(32)
        import_btn.clicked.connect(self._import_knowledge_files)
        lay.addWidget(import_btn)
        rebuild_btn = QPushButton("重新建立资料索引")
        rebuild_btn.clicked.connect(self._rebuild_knowledge_index)
        lay.addWidget(rebuild_btn)
        self._hint(lay, "导入的资料会复制到当前角色目录。聊天会自由检索相关内容，无需维护剧情进度或微调模型。")
        open_knowledge_btn = QPushButton("打开当前角色资料文件夹")
        open_knowledge_btn.clicked.connect(self._open_knowledge_folder)
        lay.addWidget(open_knowledge_btn)
        self._refresh_knowledge_status()
        lay.addStretch()
        return page

    def _open_page(self, key: str):
        """Route dashboard actions through the same navigation state as clicks."""
        self._last_page_key = key
        self._switch_page(key)
        for index in range(self._tree.topLevelItemCount()):
            parent = self._tree.topLevelItem(index)
            if parent.data(0, Qt.UserRole) == key:
                self._tree.setCurrentItem(parent)
                return
            for child_index in range(parent.childCount()):
                child = parent.child(child_index)
                if child.data(0, Qt.UserRole) == key:
                    parent.setExpanded(True)
                    self._tree.setCurrentItem(child)
                    return

    def _knowledge_base(self):
        return KnowledgeBase(self._base_dir / "characters" / self._current_char)

    def _refresh_knowledge_status(self):
        base = self._knowledge_base()
        summary = base.source_summary()
        labels = {"world": "世界观", "character": "角色设定", "dialogue": "对话示例"}
        status = "，".join(f"{labels.get(kind, kind)} {count}" for kind, count in summary.items())
        self._knowledge_status.setText(f"当前资料库：{status or '暂无资料'}（单位：检索片段）。")

    def _import_knowledge_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "导入角色资料", "", "资料文件 (*.txt *.md *.markdown *.json)")
        if not files:
            return
        copied, errors = self._knowledge_base().import_files(
            files, self._knowledge_type.currentData())
        self._refresh_knowledge_status()
        message = f"已导入 {copied} 个「{self._knowledge_type.currentText()}」文件。"
        if errors:
            message += "\n" + "\n".join(errors)
        QMessageBox.information(self, "角色资料库", message)

    def _rebuild_knowledge_index(self):
        count = self._knowledge_base().rebuild()
        self._refresh_knowledge_status()
        QMessageBox.information(self, "角色资料库", f"已建立 {count} 个可检索片段。")

    def _open_knowledge_folder(self):
        folder = self._knowledge_base().sources_dir
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ═══════════════════════════════════
    # AI 模型
    # ═══════════════════════════════════

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

    def _sync_tts_provider_fields(self, *_args):
        """Switch TTS forms without clearing local or cloud settings."""
        is_cloud = self._tts_provider.currentData() == "gpt_sovits_remote"
        for name in ("tts_model", "tts_local_url", "tts_local_config"):
            self._tts_rows[name].setVisible(not is_cloud)
        for name in ("tts_api_url", "tts_api_key", "tts_remote_reference"):
            self._tts_rows[name].setVisible(is_cloud)
        self._refresh_service_status_cards()

    def _sync_asr_provider_fields(self, *_args):
        """Switch ASR forms without mutating either backend's draft values."""
        is_cloud = self._asr_provider.currentData() == "cloud"
        local_names = ("asr_engine", "asr_model", "asr_device", "asr_compute")
        cloud_names = ("asr_api_url", "asr_api_key", "asr_api_model", "asr_api_language")
        for name in local_names:
            self._asr_rows[name].setVisible(not is_cloud)
        for name in cloud_names:
            self._asr_rows[name].setVisible(is_cloud)
        self._asr_discover_button.setVisible(is_cloud)
        self._asr_discover_status.setVisible(is_cloud)
        self._asr_model_picker.setVisible(is_cloud and self._asr_model_picker.count() > 0)
        self._refresh_service_status_cards()

    def _refresh_service_status_cards(self, *_args):
        """Reflect the in-progress form, not only the last saved config."""
        if hasattr(self, "_ai_status_card"):
            self._ai_status_card.set_state(bool(
                self._ai_url.text().strip()
                and (is_local_endpoint(self._ai_url.text().strip())
                     or self._ai_key.text().strip() or self.config.get_secret("llm")
                     or self.config.get("llm", "api_key", default=""))
                and self._ai_model.text().strip()
            ))
        if hasattr(self, "_tts_status_card"):
            cloud = self._tts_provider.currentData() == "gpt_sovits_remote"
            ready = self._tts_enabled.isChecked() and (
                bool(self._tts_model.text().strip()) if not cloud else bool(
                    self._tts_api_url.text().strip()
                    and self._tts_remote_reference.text().strip()
                )
            )
            self._tts_status_card.set_state(ready)
        if hasattr(self, "_asr_status_card"):
            cloud = self._asr_provider.currentData() == "cloud"
            ready = self._asr_enabled.isChecked() and (
                bool(self._asr_model.text().strip()) if not cloud else bool(
                    self._asr_api_url.text().strip()
                    and (is_local_endpoint(self._asr_api_url.text().strip())
                         or self._asr_api_key.text().strip() or self.config.get_secret("asr")
                         or self.config.get("asr", "api_key", default=""))
                    and self._asr_api_model.text().strip()
                )
            )
            self._asr_status_card.set_state(ready)
        if hasattr(self, "_vision_status_card"):
            self._vision_status_card.set_state(vision_connection_ready(
                self._vision_url.text().strip(), self._vision_model.text().strip(),
                self._vision_allow_cloud.isChecked(), self._vision_enabled.isChecked(),
            ))

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

    def open_page(self, key: str) -> None:
        """Public routing hook used by first-run setup and tray shortcuts."""
        self._open_page(key)

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
            "opacity": (
                safe(getattr(self, "_opacity", None),
                     type("", (), {"value": lambda: 100})()
                     ).value() / 100.0
                if safe(getattr(self, "_opacity", None))
                else 1.0
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
            "idle_interval": (
                safe(getattr(self, "_idle_interval", None),
                     type("", (), {"value": lambda: 30})()
                     ).value()
                if safe(getattr(self, "_idle_interval", None))
                else 30
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

        s["tts"] = {"enabled": safe(getattr(self, "_tts_enabled", None)).isChecked() if safe(getattr(self, "_tts_enabled", None)) else False,
                    "model_path": safe(getattr(self, "_tts_model", None)).text().strip() if safe(getattr(self, "_tts_model", None)) else "",
                    "local_api_url": safe(getattr(self, "_tts_local_url", None)).text().strip() if safe(getattr(self, "_tts_local_url", None)) else "http://127.0.0.1:9880",
                    "local_config": safe(getattr(self, "_tts_local_config", None)).text().strip() if safe(getattr(self, "_tts_local_config", None)) else "GPT_SoVITS/configs/noir_v2proplus.yaml",
                    "remote_reference_audio": safe(getattr(self, "_tts_remote_reference", None)).text().strip() if safe(getattr(self, "_tts_remote_reference", None)) else "",
                    "translate_to_japanese": safe(getattr(self, "_tts_translate", None)).isChecked() if safe(getattr(self, "_tts_translate", None)) else True,
                    "speed": safe(getattr(self, "_tts_speed", None)).value() / 100.0 if safe(getattr(self, "_tts_speed", None)) else 1.0,
                    "auto_play": safe(getattr(self, "_tts_auto_play", None)).isChecked() if safe(getattr(self, "_tts_auto_play", None)) else True,
                    "provider": safe(getattr(self, "_tts_provider", None)).currentData() if safe(getattr(self, "_tts_provider", None)) else "gpt_sovits_local",
                    "base_url": safe(getattr(self, "_tts_api_url", None)).text().strip() if safe(getattr(self, "_tts_api_url", None)) else "",
                    "api_key": safe(getattr(self, "_tts_api_key", None)).text().strip() if safe(getattr(self, "_tts_api_key", None)) else "",
                    "model": "", "voice": ""}
        s["asr"] = {"enabled": safe(getattr(self, "_asr_enabled", None)).isChecked() if safe(getattr(self, "_asr_enabled", None)) else False,
                    "model_path": safe(getattr(self, "_asr_model", None)).text().strip() if safe(getattr(self, "_asr_model", None)) else "",
                    "hotkey": safe(getattr(self, "_asr_hotkey", None)).text().strip() if safe(getattr(self, "_asr_hotkey", None)) else "Ctrl+Alt+Space",
                    "device": safe(getattr(self, "_asr_device", None)).currentData() if safe(getattr(self, "_asr_device", None)) else "cpu",
                    "compute_type": safe(getattr(self, "_asr_compute", None)).currentData() if safe(getattr(self, "_asr_compute", None)) else "int8",
                    "auto_send": safe(getattr(self, "_asr_auto_send", None)).isChecked() if safe(getattr(self, "_asr_auto_send", None)) else True,
                    "provider": safe(getattr(self, "_asr_provider", None)).currentData() if safe(getattr(self, "_asr_provider", None)) else "local",
                    "base_url": safe(getattr(self, "_asr_api_url", None)).text().strip() if safe(getattr(self, "_asr_api_url", None)) else "",
                    "api_key": safe(getattr(self, "_asr_api_key", None)).text().strip() if safe(getattr(self, "_asr_api_key", None)) else "",
                    "model": safe(getattr(self, "_asr_api_model", None)).text().strip() if safe(getattr(self, "_asr_api_model", None)) else "whisper-1",
                    "language": safe(getattr(self, "_asr_api_language", None)).text().strip() if safe(getattr(self, "_asr_api_language", None)) else ""}
        s["screen_capture"] = {"keep_captures": safe(getattr(self, "_screen_keep", None)).isChecked() if safe(getattr(self, "_screen_keep", None)) else False,
                               "hotkey": safe(getattr(self, "_screen_hotkey", None)).text().strip() if safe(getattr(self, "_screen_hotkey", None)) else "Ctrl+Alt+O",
                               "cloud_first": safe(getattr(self, "_screen_cloud_first", None)).isChecked() if safe(getattr(self, "_screen_cloud_first", None)) else True,
                               "auto_observe": safe(getattr(self, "_screen_auto_observe", None)).isChecked() if safe(getattr(self, "_screen_auto_observe", None)) else False,
                               "observe_min_interval": (safe(getattr(self, "_screen_observe_min", None)).value() if safe(getattr(self, "_screen_observe_min", None)) else 5) * 60,
                               "observe_max_interval": (safe(getattr(self, "_screen_observe_max", None)).value() if safe(getattr(self, "_screen_observe_max", None)) else 15) * 60,
                               "observe_cooldown": (safe(getattr(self, "_screen_observe_cooldown", None)).value() if safe(getattr(self, "_screen_observe_cooldown", None)) else 10) * 60,
                               "vision_max_dimension": safe(getattr(self, "_screen_vision_max_dimension", None)).value() if safe(getattr(self, "_screen_vision_max_dimension", None)) else 1280}
        s["vision"] = {"enabled": safe(getattr(self, "_vision_enabled", None)).isChecked() if safe(getattr(self, "_vision_enabled", None)) else False,
                       "base_url": safe(getattr(self, "_vision_url", None)).text().strip() if safe(getattr(self, "_vision_url", None)) else "",
                       "model": safe(getattr(self, "_vision_model", None)).text().strip() if safe(getattr(self, "_vision_model", None)) else "",
                       "api_key": safe(getattr(self, "_vision_key", None)).text().strip() if safe(getattr(self, "_vision_key", None)) else "",
                       "allow_cloud": safe(getattr(self, "_vision_allow_cloud", None)).isChecked() if safe(getattr(self, "_vision_allow_cloud", None)) else False}
        s["knowledge"] = {
            "enabled": safe(getattr(self, "_knowledge_enabled", None)).isChecked() if safe(getattr(self, "_knowledge_enabled", None)) else True,
        }

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
        applied, error = apply_settings(self.config, v)
        if error:
            QMessageBox.warning(self, "API Key 无效", error)
            return False
        self._save_character_prompt()
        self.apply_clicked.emit(applied)
        self._settings_baseline = self._settings_snapshot()
        self._refresh_dirty_state()
        return True

    def _character_config_path(self) -> Path:
        return self._base_dir / "characters" / self._current_char / "config.json"

    def _character_prompt(self) -> dict:
        path = self._character_config_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            data = {}
        prompt = data.get("character_prompt")
        if isinstance(prompt, dict):
            return prompt
        return {}

    def _save_character_prompt(self):
        save_character_prompt(
            self._character_config_path(), self._system_prompt.toPlainText(),
            self._format_prompt.toPlainText(),
        )

    def _on_scale_slider(self, v):
        self._scale_label.setText(f"{v}%")
        self.scale_changed.emit(v / 100.0)

    def _on_ok(self):
        if self._on_apply():
            self.accept()
