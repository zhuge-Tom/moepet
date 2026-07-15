"""设置窗口

QTreeWidget 导航 + 搜索 + 折叠动画 + 子项弹菜单。
完整版：通用设置 / 角色设置(接口+立绘) / AI模型 / TTS / ASR / 关于。
"""

import os
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QSlider, QCheckBox, QComboBox, QPushButton,
    QScrollArea, QFrame, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QSizePolicy, QMenu, QTextEdit, QSpinBox, QGroupBox,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal, QEvent, QTimer
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
    ("🔊", "语音合成", "tts", False, []),
    ("🎤", "语音输入", "asr", False, []),
    ("ℹ", "关于", "about", True, []),
]
NAV_WIDE = 160
NAV_NARROW = 48
ANIM_MS = 220
ROW_H = 36


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

        self.setWindowTitle("Moepet 设置")
        self.setMinimumSize(520, 460)
        self.resize(680, 540)
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
        frame.setStyleSheet("QFrame { background: #2c3e50; border-right: 1px solid #1a252f; }")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 描述行
        self._desc_row = QHBoxLayout()
        self._desc_row.setContentsMargins(6, 6, 6, 2)
        self._desc_row.setSpacing(4)
        self._desc_label = QLabel("Moepet")
        self._desc_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #ecf0f1; background: transparent;")
        self._desc_row.addWidget(self._desc_label, 1)

        self._collapse_top = QPushButton("▶")
        self._collapse_top.setFixedSize(NAV_NARROW - 8, 24)
        self._collapse_top.setToolTip("展开导航")
        self._collapse_top.setStyleSheet(
            "QPushButton { background: transparent; border: none; font-size: 14px; color: #bdc3c7; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.1); }")
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
            "QPushButton { background: transparent; border: none; font-size: 16px; color: #bdc3c7; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.1); }")
        self._collapse_side.clicked.connect(self._toggle_nav)
        self._tool_row.addWidget(self._collapse_side)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("查找设置...")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setFixedHeight(28)
        self.search_box.setStyleSheet(
            "QLineEdit { border: 1px solid #34495e; border-radius: 6px; padding: 2px 6px;"
            "font-size: 11px; background: #34495e; color: #ecf0f1; }"
            "QLineEdit:focus { border-color: #e94560; }")
        self.search_box.textChanged.connect(self._on_search)
        self._tool_row.addWidget(self.search_box, 1)

        self._search_icon = QPushButton("🔍")
        self._search_icon.setFixedSize(30, 28)
        self._search_icon.setToolTip("搜索")
        self._search_icon.setStyleSheet(
            "QPushButton { background: transparent; border: none; font-size: 13px; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.1); }")
        self._search_icon.clicked.connect(self._expand_nav)
        self._search_icon.hide()
        self._tool_row.addWidget(self._search_icon)
        layout.addLayout(self._tool_row)

        # 树形导航
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(16)
        self._tree.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._tree.verticalScrollBar().setEnabled(False)
        self._tree.setAnimated(True)
        self._tree.setStyleSheet("""
            QTreeWidget { background: transparent; border: none; outline: none; font-size: 13px; }
            QTreeWidget::item { padding: 7px 6px; border-radius: 6px; color: #bdc3c7; }
            QTreeWidget::item:selected { background: #e94560; color: #fff; font-weight: bold; }
            QTreeWidget::item:hover:!selected { background: rgba(255,255,255,0.08); }""")

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
        self._tree.viewport().installEventFilter(self)
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

    def eventFilter(self, obj, event):
        if obj is self._tree.viewport() and event.type() == QEvent.MouseButtonRelease:
            item = self._tree.itemAt(event.pos())
            if item:
                self._on_item_clicked(item, 0)
                return True
        return super().eventFilter(obj, event)

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
            p.setHidden(not any_vis and not (not text.strip() or text.strip().lower() in p.text(0).lower()))

    # ═══════════════════════════════════
    # 右侧 + 页面路由
    # ═══════════════════════════════════

    def _on_tree_changed(self, cur, prev):
        if not cur:
            return
        # 有子项的节点不触发页面切换（只弹菜单）
        children = cur.data(0, Qt.UserRole + 1)
        if children:
            return
        self._switch_page(cur.data(0, Qt.UserRole))

    def _on_item_clicked(self, item, col):
        children = item.data(0, Qt.UserRole + 1)
        if children:
            self._popup_children_menu(item, children)
            # 恢复到上一个选中的非父节点，避免高亮停在父节点上
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
            self._last_page_key = item.data(0, Qt.UserRole)
            self._switch_page(self._last_page_key)

    def _popup_children_menu(self, item, children):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #2c3e50; color: #ecf0f1; border: 1px solid #e94560;
                    border-radius: 6px; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background: #e94560; }""")
        for emoji, text, key in children:
            action = QAction(f"{emoji}  {text}", self)
            action.setData(key)
            action.triggered.connect(lambda checked, k=key: self._switch_page(k))
            menu.addAction(action)
        rect = self._tree.visualItemRect(item)
        pos = self._tree.viewport().mapToGlobal(rect.bottomLeft())
        menu.exec(pos)

    def _switch_page(self, key):
        while self._card_layout.count():
            w = self._card_layout.takeAt(0)
            if w.widget():
                w.widget().deleteLater()

        titles = {
            "general": "通用设置", "character": "角色设置",
            "character_api": "接口设置", "character_sprites": "立绘设置",
            "ai": "AI 模型", "tts": "语音合成", "asr": "语音输入", "about": "关于",
        }
        self._page_title.setText(titles.get(key, ""))

        renderers = {
            "general": self._page_general,
            "character": self._page_character_parent,
            "character_api": self._page_character_api,
            "character_sprites": self._page_character_sprites,
            "ai": self._page_ai,
            "tts": self._page_tts,
            "asr": self._page_asr,
            "about": self._page_about,
        }
        renderers.get(key, self._page_general)()
        self._card_layout.addStretch()

    def _build_right(self):
        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(20, 12, 20, 16)
        layout.setSpacing(10)

        self._page_title = QLabel("通用设置")
        self._page_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1e293b;")
        layout.addWidget(self._page_title, alignment=Qt.AlignLeft)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 6px; background: transparent; border-radius: 3px; }"
            "QScrollBar::handle:vertical { background: #c8ccd4; border-radius: 3px; min-height: 30px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }")

        self.card = QFrame()
        self.card.setStyleSheet("QFrame { background: #fff; border-radius: 14px; border: 1px solid #e2e6ed; }")
        self._card_layout = QVBoxLayout(self.card)
        self._card_layout.setContentsMargins(24, 20, 24, 20)
        self._card_layout.setSpacing(10)
        scroll.setWidget(self.card)
        layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        for text, slot, pri in [("应用", self._on_apply, False), ("确定", self._on_ok, True), ("取消", self.reject, False)]:
            b = QPushButton(text)
            if pri:
                b.setStyleSheet("QPushButton { background: #e94560; color: #fff; border: none; border-radius: 7px; padding: 7px 22px; font-size: 13px; }"
                                "QPushButton:hover { background: #ff6b6b; }")
            else:
                b.setStyleSheet("QPushButton { background: #fff; color: #444; border: 1px solid #d3d7de; border-radius: 7px; padding: 7px 22px; font-size: 13px; }"
                                "QPushButton:hover { background: #f5f6fa; }")
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        layout.addLayout(btn_row)
        return right

    # ─── 通用控件 ─────────────────────────────

    def _sec(self, t):
        label = QLabel(t)
        label.setStyleSheet("font-weight: bold; font-size: 13px; color: #64748b; margin-top: 4px;")
        self._card_layout.addWidget(label)

    def _row(self, label_text: str, widget, stretch_label=True):
        """标签 + 控件 的水平行"""
        row = QHBoxLayout()
        row.setSpacing(12)
        lbl = QLabel(label_text)
        lbl.setStyleSheet("font-size: 13px; color: #2c3e50;")
        lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        self._card_layout.addLayout(row)
        return widget

    def _line_edit(self, placeholder="", echo_mode=QLineEdit.Normal):
        le = QLineEdit()
        le.setPlaceholderText(placeholder)
        le.setEchoMode(echo_mode)
        le.setFixedHeight(30)
        le.setStyleSheet(
            "QLineEdit { border: 1px solid #d3d7de; border-radius: 6px; padding: 4px 10px; font-size: 13px; }"
            "QLineEdit:focus { border-color: #e94560; }")
        return le

    def _ph(self, t):
        label = QLabel(t)
        label.setStyleSheet("color: #94a3b8; font-size: 13px; padding: 20px;")
        label.setAlignment(Qt.AlignCenter)
        self._card_layout.addWidget(label)

    # ═══════════════════════════════════
    # 通用设置
    # ═══════════════════════════════════

    def _page_general(self):
        self._sec("软件设置")

        # 角色选择 - 分两行：标签一行，控件一行
        char_lbl = QLabel("角色选择")
        char_lbl.setStyleSheet("font-size: 13px; color: #2c3e50;")
        self._card_layout.addWidget(char_lbl)

        self._char_combo = QComboBox()
        self._char_combo.setFixedHeight(30)
        self._char_combo.setStyleSheet("QComboBox { border: 1px solid #d3d7de; border-radius: 6px; padding: 4px 10px; font-size: 13px; }")
        for n in self._characters:
            self._char_combo.addItem(n)
        idx = self._char_combo.findText(self._current_char)
        if idx >= 0:
            self._char_combo.setCurrentIndex(idx)
        self._card_layout.addWidget(self._char_combo)

        open_folder_btn = QPushButton("📂 打开角色文件夹")
        open_folder_btn.setFixedHeight(28)
        open_folder_btn.setStyleSheet(
            "QPushButton { background: #f5f7fa; color: #444; border: 1px solid #d3d7de; border-radius: 6px; padding: 4px 12px; font-size: 12px; }"
            "QPushButton:hover { background: #e8ecf1; }")
        open_folder_btn.clicked.connect(self._open_characters_folder)
        self._card_layout.addWidget(open_folder_btn)

        self._auto_start_cb = QCheckBox("开机自启")
        self._auto_start_cb.setChecked(self.config.get("general", "auto_start", default=False))
        self._card_layout.addWidget(self._auto_start_cb)

        self._sec("窗口设置")

        self._always_top_cb = QCheckBox("始终置顶")
        self._always_top_cb.setChecked(self.config.get("window", "always_on_top", default=True))
        self._card_layout.addWidget(self._always_top_cb)

        # 缩放 - 单独一行
        scale_lbl = QLabel("立绘缩放")
        scale_lbl.setStyleSheet("font-size: 13px; color: #2c3e50;")
        self._card_layout.addWidget(scale_lbl)

        scale_row = QHBoxLayout()
        scale_row.setSpacing(8)
        self._scale_slider = QSlider(Qt.Horizontal)
        self._scale_slider.setRange(10, 200)
        self._scale_slider.setValue(int(self.config.get("window", "scale", default=0.5) * 100))
        self._scale_slider.valueChanged.connect(self._on_scale_slider)
        self._scale_slider.setFixedHeight(20)
        self._scale_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 4px; background: #e2e6ed; border-radius: 2px; }"
            "QSlider::handle:horizontal { width: 14px; height: 14px; margin: -5px 0; background: #e94560; border-radius: 7px; }")

        self._scale_label = QLabel(f"{self._scale_slider.value()}%")
        self._scale_label.setFixedWidth(42)
        self._scale_label.setStyleSheet("color: #e94560; font-weight: bold; font-size: 13px;")

        scale_row.addWidget(self._scale_slider, 1)
        scale_row.addWidget(self._scale_label)
        self._card_layout.addLayout(scale_row)

        # 逐字速度
        self._typing_speed = QSpinBox()
        self._typing_speed.setRange(10, 500)
        self._typing_speed.setValue(self.config.get("general", "typing_speed", default=40))
        self._typing_speed.setSuffix(" ms/字")
        self._typing_speed.setFixedHeight(30)
        self._typing_speed.setMinimumWidth(120)
        self._typing_speed.setStyleSheet("QSpinBox { border: 1px solid #d3d7de; border-radius: 6px; padding: 4px 8px; font-size: 13px; }")
        self._row("逐字显示速度", self._typing_speed)

        # 对话框缩放
        self._dialog_scale = QSpinBox()
        self._dialog_scale.setRange(50, 200)
        self._dialog_scale.setValue(self.config.get("general", "dialog_scale", default=100))
        self._dialog_scale.setSuffix(" %")
        self._dialog_scale.setFixedHeight(30)
        self._dialog_scale.setMinimumWidth(120)
        self._dialog_scale.setStyleSheet("QSpinBox { border: 1px solid #d3d7de; border-radius: 6px; padding: 4px 8px; font-size: 13px; }")
        self._row("对话框缩放", self._dialog_scale)

        self._sec("行为")

        self._click_combo = QComboBox()
        self._click_combo.addItem("切换下一张立绘", "switch_sprite")
        self._click_combo.addItem("弹跳动画", "bounce")
        self._click_combo.addItem("无反应", "none")
        self._click_combo.setFixedHeight(30)
        self._click_combo.setStyleSheet("QComboBox { border: 1px solid #d3d7de; border-radius: 6px; padding: 6px 10px; font-size: 13px; }")
        current = self.config.get("behavior", "click_action", default="switch_sprite")
        idx = self._click_combo.findData(current)
        if idx >= 0:
            self._click_combo.setCurrentIndex(idx)
        self._row("点击立绘", self._click_combo)

        self._auto_idle_cb = QCheckBox("自动待机动画")
        self._auto_idle_cb.setChecked(self.config.get("behavior", "auto_idle", default=True))
        self._card_layout.addWidget(self._auto_idle_cb)

    def _open_characters_folder(self):
        folder = self._base_dir / "characters"
        if folder.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ═══════════════════════════════════
    # 角色设置 > 接口设置
    # ═══════════════════════════════════

    def _page_character_api(self):
        self._sec("对话设置")

        prompt_lbl = QLabel("角色提示词（system prompt）")
        prompt_lbl.setStyleSheet("font-size: 13px; color: #2c3e50; font-weight: bold;")
        self._card_layout.addWidget(prompt_lbl)

        self._system_prompt = QTextEdit()
        self._system_prompt.setPlaceholderText("设定角色的性格、说话方式、回复格式...")
        self._system_prompt.setFixedHeight(120)
        self._system_prompt.setPlainText(self.config.get("character_prompt", "system_prompt", default=""))
        self._system_prompt.setStyleSheet(
            "QTextEdit { border: 1px solid #d3d7de; border-radius: 8px; padding: 8px; font-size: 13px; }"
            "QTextEdit:focus { border-color: #e94560; }")
        self._card_layout.addWidget(self._system_prompt)

        hint = QLabel("提示词决定了角色的性格和回复风格")
        hint.setStyleSheet("color: #999; font-size: 11px;")
        self._card_layout.addWidget(hint)

        self._card_layout.addSpacing(8)
        self._sec("格式提示词（可选）")

        self._format_prompt = QTextEdit()
        self._format_prompt.setPlaceholderText("例如：每句话前加上心情标签，格式为 {心情}|{回复}")
        self._format_prompt.setFixedHeight(80)
        self._format_prompt.setPlainText(self.config.get("character_prompt", "format_prompt", default=""))
        self._format_prompt.setStyleSheet(
            "QTextEdit { border: 1px solid #d3d7de; border-radius: 8px; padding: 8px; font-size: 13px; }"
            "QTextEdit:focus { border-color: #e94560; }")
        self._card_layout.addWidget(self._format_prompt)

    # ═══════════════════════════════════
    # 角色设置 > 立绘设置
    # ═══════════════════════════════════

    def _page_character_sprites(self):
        self._sec("当前角色立绘")

        self._sprite_list = QTreeWidget()
        self._sprite_list.setHeaderHidden(True)
        self._sprite_list.setStyleSheet(
            "QTreeWidget { border: 1px solid #e2e6ed; border-radius: 8px; padding: 4px; font-size: 13px; }"
            "QTreeWidget::item { padding: 6px 10px; border-radius: 4px; }"
            "QTreeWidget::item:selected { background: #fce4ec; color: #e94560; }")

        char_dir = self._base_dir / "characters" / self._current_char / "sprites"
        if char_dir.exists():
            for img in sorted(char_dir.glob("*.png")):
                item = QTreeWidgetItem([f"🖼️  {img.stem}  ({img.stat().st_size // 1024}KB)"])
                item.setData(0, Qt.UserRole, str(img))
                self._sprite_list.addTopLevelItem(item)

        self._sprite_list.setFixedHeight(140)
        self._card_layout.addWidget(self._sprite_list)

        row = QHBoxLayout()
        select_label = QLabel("选择后点击「应用」切换角色")
        select_label.setStyleSheet("color: #999; font-size: 11px;")
        row.addWidget(select_label)
        row.addStretch()

        open_sprite_btn = QPushButton("📂 打开立绘文件夹")
        open_sprite_btn.setStyleSheet(
            "QPushButton { background: #f5f7fa; color: #444; border: 1px solid #d3d7de; border-radius: 6px; padding: 4px 12px; font-size: 12px; }"
            "QPushButton:hover { background: #e8ecf1; }")
        open_sprite_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(char_dir))))
        row.addWidget(open_sprite_btn)
        self._card_layout.addLayout(row)

        hint = QLabel("将 .png 立绘文件放入 sprites 文件夹即可自动加载")
        hint.setStyleSheet("color: #999; font-size: 11px;")
        self._card_layout.addWidget(hint)

    # ═══════════════════════════════════
    # AI 模型
    # ═══════════════════════════════════

    def _page_ai(self):
        self._sec("OpenAI 兼容 API")

        self._ai_url = self._line_edit("https://api.deepseek.com/v1")
        self._ai_url.setText(self.config.get("llm", "base_url", default=""))
        self._row("Base URL", self._ai_url)

        url_hint = QLabel("支持 DeepSeek / OpenAI / 本地 Ollama 等 OpenAI 兼容接口")
        url_hint.setStyleSheet("color: #999; font-size: 11px; margin-left: 4px;")
        self._card_layout.addWidget(url_hint)

        self._ai_key = self._line_edit("sk-xxxx", QLineEdit.Password)
        self._ai_key.setText(self.config.get("llm", "api_key", default=""))
        self._row("API Key", self._ai_key)

        self._ai_model = self._line_edit("deepseek-chat / gpt-4o-mini / ...")
        self._ai_model.setText(self.config.get("llm", "model", default=""))
        self._row("Model", self._ai_model)

        self._sec("高级设定")

        self._ai_stream_cb = QCheckBox("启用流式输出（逐字显示）")
        self._ai_stream_cb.setChecked(self.config.get("llm", "stream", default=True))
        self._card_layout.addWidget(self._ai_stream_cb)

        self._ai_post = self._line_edit("例如 <think>.*?</think>")
        self._ai_post.setText(self.config.get("llm", "post_processing", default=""))
        self._row("回复后处理（正则）", self._ai_post)

        post_hint = QLabel("用正则表达式删除回复中不需要的部分，如模型思考过程")
        post_hint.setStyleSheet("color: #999; font-size: 11px; margin-left: 4px;")
        self._card_layout.addWidget(post_hint)

        self._ai_ignore_err_cb = QCheckBox("忽略格式错误")
        self._ai_ignore_err_cb.setChecked(self.config.get("llm", "ignore_format_error", default=True))
        self._card_layout.addWidget(self._ai_ignore_err_cb)

        # 测试连接按钮
        self._card_layout.addSpacing(4)
        test_btn = QPushButton("🔗 测试连接")
        test_btn.setFixedHeight(32)
        test_btn.setStyleSheet(
            "QPushButton { background: #3498db; color: #fff; border: none; border-radius: 7px; padding: 7px 22px; font-size: 13px; }"
            "QPushButton:hover { background: #2980b9; }")
        test_btn.clicked.connect(self._test_connection)
        self._card_layout.addWidget(test_btn)

        self._test_status = QLabel("")
        self._test_status.setWordWrap(True)
        self._test_status.setStyleSheet("font-size: 12px; padding: 4px;")
        self._card_layout.addWidget(self._test_status)

    def _test_connection(self):
        """测试 API 连接"""
        from core.llm_service import LLMService
        self._test_status.setText("连接中...")
        self._test_status.setStyleSheet("color: #3498db; font-size: 12px; padding: 4px;")

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
        self._test_status.setStyleSheet("color: #27ae60; font-size: 12px; padding: 4px;")

    def _on_test_error(self, err):
        self._test_status.setText(f"❌ {err}")
        self._test_status.setStyleSheet("color: #e74c3c; font-size: 12px; padding: 4px;")

    # ═══════════════════════════════════
    # TTS / ASR / 关于
    # ═══════════════════════════════════

    def _page_character_parent(self):
        self._ph("请在下方选择「接口设置」或「立绘设置」")

    def _page_tts(self):
        self._ph("语音合成（TTS）将在后续版本中支持\n音色训练计划中")

    def _page_asr(self):
        self._ph("语音输入（ASR）将在后续版本中支持")

    def _page_about(self):
        about = QLabel(
            "Moepet - 萌系桌面宠物\n"
            "基于 PySide6 的桌面宠物应用\n\n"
            "支持多角色切换、AI 对话、Galgame 风格对话框、\n"
            "立绘动画演出、系统托盘等功能。\n\n"
            "GitHub: zhuge-Tom/moepet")
        about.setStyleSheet("color: #555; font-size: 13px; padding: 16px;")
        about.setAlignment(Qt.AlignCenter)
        self._card_layout.addWidget(about)

    # ─── 配置收集 ─────────────────────────────

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
        s["current_character"] = safe(getattr(self, "_char_combo", None), type("", (), {"currentText": lambda: self._current_char})()).currentText() if safe(getattr(self, "_char_combo", None)) else self._current_char
        s["window"] = {
            "scale": safe(getattr(self, "_scale_slider", None), type("", (), {"value": lambda: 50})()).value() / 100.0 if safe(getattr(self, "_scale_slider", None)) else self.config.get("window", "scale", default=0.5),
            "always_on_top": safe(getattr(self, "_always_top_cb", None), type("", (), {"isChecked": lambda: True})()).isChecked() if safe(getattr(self, "_always_top_cb", None)) else True,
        }
        s["behavior"] = {
            "click_action": safe(getattr(self, "_click_combo", None), type("", (), {"currentData": lambda: "switch_sprite"})()).currentData() if safe(getattr(self, "_click_combo", None)) else "switch_sprite",
            "auto_idle": safe(getattr(self, "_auto_idle_cb", None), type("", (), {"isChecked": lambda: True})()).isChecked() if safe(getattr(self, "_auto_idle_cb", None)) else True,
        }
        s["general"] = {
            "typing_speed": safe(getattr(self, "_typing_speed", None), type("", (), {"value": lambda: 40})()).value() if safe(getattr(self, "_typing_speed", None)) else 40,
            "dialog_scale": safe(getattr(self, "_dialog_scale", None), type("", (), {"value": lambda: 100})()).value() if safe(getattr(self, "_dialog_scale", None)) else 100,
            "auto_start": safe(getattr(self, "_auto_start_cb", None), type("", (), {"isChecked": lambda: False})()).isChecked() if safe(getattr(self, "_auto_start_cb", None)) else False,
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
                "post_processing": ai_post.text().strip() if ai_post else "",
                "ignore_format_error": ai_ignore.isChecked() if ai_ignore else True,
            }

        # 角色提示词
        sys_prompt = safe(getattr(self, "_system_prompt", None))
        fmt_prompt = safe(getattr(self, "_format_prompt", None))
        if sys_prompt or fmt_prompt:
            s["character_prompt"] = {
                "system_prompt": sys_prompt.toPlainText() if sys_prompt else "",
                "format_prompt": fmt_prompt.toPlainText() if fmt_prompt else "",
            }

        return s

    def get_new_character(self) -> str | None:
        cl = getattr(self, "_char_combo", None)
        if not cl:
            return None
        return cl.currentText() if cl.currentText() != self._current_char else None

    def _on_apply(self):
        v = self._collect_settings()
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
