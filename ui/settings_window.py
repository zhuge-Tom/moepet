"""设置窗口

QTreeWidget 导航 + 搜索 + 折叠动画 + 子项弹菜单。
保留原版交互设计，使用当前深色主题配色。
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QSlider, QCheckBox, QComboBox, QPushButton,
    QScrollArea, QFrame, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QSizePolicy, QMenu,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal, QEvent
from PySide6.QtGui import QPainter, QFont, QIcon, QPixmap, QAction

from core.config import Config

NAV_TREE = [
    ("⚙", "通用设置", "general", True, []),
    ("🎭", "角色设置", "character", True, [
        ("🔌", "接口设置", "character_api"),
        ("🖼️", "立绘设置", "character_sprites"),
    ]),
    ("🤖", "AI 模型", "ai", False, []),
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

    def __init__(self, config: Config, characters: list[str], current_char: str, parent=None):
        super().__init__(parent)
        self.config = config
        self._characters = characters
        self._current_char = current_char
        self._collapsed = False

        self.setWindowTitle("Moepet 设置")
        self.setMinimumSize(480, 420)
        self.resize(640, 480)
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
            "QFrame { background: #2c3e50; border-right: 1px solid #1a252f; }"
        )

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 描述行（含隐藏的折叠按钮，收拢后才显示）
        self._desc_row = QHBoxLayout()
        self._desc_row.setContentsMargins(6, 6, 6, 2)
        self._desc_row.setSpacing(4)

        self._desc_label = QLabel("Moepet")
        self._desc_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #ecf0f1; background: transparent;"
        )
        self._desc_row.addWidget(self._desc_label, 1)

        self._collapse_top = QPushButton("▶")
        self._collapse_top.setFixedSize(NAV_NARROW - 8, 24)
        self._collapse_top.setToolTip("展开导航")
        self._collapse_top.setStyleSheet(
            "QPushButton { background: transparent; border: none; font-size: 14px;"
            "color: #bdc3c7; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.1); }"
        )
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
            "QPushButton { background: transparent; border: none; font-size: 16px;"
            "color: #bdc3c7; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.1); }"
        )
        self._collapse_side.clicked.connect(self._toggle_nav)
        self._tool_row.addWidget(self._collapse_side)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("查找设置...")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setFixedHeight(28)
        self.search_box.setStyleSheet(
            "QLineEdit { border: 1px solid #34495e; border-radius: 6px; padding: 2px 6px;"
            "font-size: 11px; background: #34495e; color: #ecf0f1; }"
            "QLineEdit:focus { border-color: #e94560; }"
        )
        self.search_box.textChanged.connect(self._on_search)
        self._tool_row.addWidget(self.search_box, 1)

        self._search_icon = QPushButton("🔍")
        self._search_icon.setFixedSize(30, 28)
        self._search_icon.setToolTip("搜索")
        self._search_icon.setStyleSheet(
            "QPushButton { background: transparent; border: none; font-size: 13px;"
            "border-radius: 4px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.1); }"
        )
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
            QTreeWidget::item:hover:!selected { background: rgba(255,255,255,0.08); }
        """)

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
        self._remove_all_children()

    def _do_expand(self):
        self._anim_nav_width(NAV_WIDE)
        self._desc_label.show()
        self._collapse_top.hide()
        self._desc_row.setContentsMargins(6, 6, 6, 2)
        self._collapse_side.show()
        self._search_icon.hide()
        self.search_box.show()
        self._tool_row.setContentsMargins(4, 2, 6, 4)
        self._restore_all_children()

    def _remove_all_children(self):
        for i in range(self._tree.topLevelItemCount()):
            p = self._tree.topLevelItem(i)
            while p.childCount() > 0:
                p.removeChild(p.child(0))

    def _restore_all_children(self):
        for i, (emoji, text, key, enabled, children) in enumerate(NAV_TREE):
            p = self._tree.topLevelItem(i)
            for ct_emoji, ct, ck in children:
                c = QTreeWidgetItem([f"{ct}"])
                c.setData(0, Qt.UserRole, ck)
                c.setIcon(0, self._icon(ct_emoji))
                p.addChild(c)

    def eventFilter(self, obj, event):
        """折叠后 viewport 点击兜底"""
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
            p.setHidden(not any_vis and not (
                not text.strip() or text.strip().lower() in p.text(0).lower()))

    # ═══════════════════════════════════
    # 右侧 + 页面
    # ═══════════════════════════════════

    def _on_tree_changed(self, cur, prev):
        if not cur:
            return
        self._switch_page(cur.data(0, Qt.UserRole))

    def _on_item_clicked(self, item, col):
        children = item.data(0, Qt.UserRole + 1)
        if children:
            self._popup_children_menu(item, children)
        else:
            self._switch_page(item.data(0, Qt.UserRole))

    def _popup_children_menu(self, item, children):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #2c3e50; color: #ecf0f1; border: 1px solid #e94560;
                    border-radius: 6px; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background: #e94560; }
        """)
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

        page_map = {}
        for _, text, k, _, _ in NAV_TREE:
            page_map[k] = text
            for ct, ct_text, ck in _[4] if isinstance(_, tuple) else []:
                pass
        # 补充子页面标题
        page_map["character_api"] = "接口设置"
        page_map["character_sprites"] = "立绘设置"
        for _, text, k, _, children in NAV_TREE:
            if k == key:
                self._page_title.setText(text)
                break
            for _, ct, ck in children:
                if ck == key:
                    self._page_title.setText(ct)
                    break

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
        fn = renderers.get(key, self._page_general)
        fn()
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
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        self.card = QFrame()
        self.card.setStyleSheet(
            "QFrame { background: #fff; border-radius: 14px; border: 1px solid #e2e6ed; }"
        )
        self._card_layout = QVBoxLayout(self.card)
        self._card_layout.setContentsMargins(24, 20, 24, 20)
        self._card_layout.setSpacing(14)

        scroll.setWidget(self.card)
        layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        apply_btn = QPushButton("应用")
        apply_btn.setStyleSheet(
            "QPushButton { background: #fff; color: #444; border: 1px solid #d3d7de;"
            "border-radius: 7px; padding: 7px 22px; font-size: 13px; }"
            "QPushButton:hover { background: #f5f6fa; }"
        )
        apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(apply_btn)

        ok_btn = QPushButton("确定")
        ok_btn.setStyleSheet(
            "QPushButton { background: #e94560; color: #fff; border: none;"
            "border-radius: 7px; padding: 7px 22px; font-size: 13px; }"
            "QPushButton:hover { background: #ff6b6b; }"
        )
        ok_btn.clicked.connect(self._on_ok)
        btn_row.addWidget(ok_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(
            "QPushButton { background: #fff; color: #444; border: 1px solid #d3d7de;"
            "border-radius: 7px; padding: 7px 22px; font-size: 13px; }"
            "QPushButton:hover { background: #f5f6fa; }"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)
        return right

    # ─── 页面实现 ─────────────────────────────

    def _sec(self, t):
        label = QLabel(t)
        label.setStyleSheet("font-weight: bold; font-size: 13px; color: #64748b; margin-top: 2px;")
        self._card_layout.addWidget(label)

    def _ph(self, t):
        label = QLabel(t)
        label.setStyleSheet("color: #94a3b8; font-size: 13px; padding: 20px;")
        label.setAlignment(Qt.AlignCenter)
        self._card_layout.addWidget(label)

    def _page_general(self):
        self._sec("窗口")

        self._always_top_cb = QCheckBox("始终置顶")
        self._always_top_cb.setChecked(self.config.get("window", "always_on_top", default=True))
        self._card_layout.addWidget(self._always_top_cb)

        self._sec("缩放")
        row = QHBoxLayout()
        self._scale_slider = QSlider(Qt.Horizontal)
        self._scale_slider.setRange(10, 200)
        self._scale_slider.setValue(int(self.config.get("window", "scale", default=0.5) * 100))
        self._scale_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 4px; background: #e2e6ed; border-radius: 2px; }"
            "QSlider::handle:horizontal { width: 14px; height: 14px; margin: -5px 0;"
            "background: #e94560; border-radius: 7px; }"
        )
        self._scale_slider.valueChanged.connect(self._on_scale_slider)

        self._scale_label = QLabel(f"{self._scale_slider.value()}%")
        self._scale_label.setFixedWidth(42)
        self._scale_label.setStyleSheet("color: #e94560; font-weight: bold; font-size: 13px;")

        row.addWidget(self._scale_slider, 1)
        row.addWidget(self._scale_label)
        self._card_layout.addLayout(row)

        self._sec("行为")
        self._click_combo = QComboBox()
        self._click_combo.addItem("切换下一张立绘", "switch_sprite")
        self._click_combo.addItem("弹跳动画", "bounce")
        self._click_combo.addItem("无反应", "none")
        self._click_combo.setStyleSheet(
            "QComboBox { border: 1px solid #d3d7de; border-radius: 6px; padding: 6px 10px; font-size: 13px; }"
        )
        current = self.config.get("behavior", "click_action", default="switch_sprite")
        idx = self._click_combo.findData(current)
        if idx >= 0:
            self._click_combo.setCurrentIndex(idx)
        self._card_layout.addWidget(self._click_combo)

        self._auto_idle_cb = QCheckBox("自动待机动画")
        self._auto_idle_cb.setChecked(self.config.get("behavior", "auto_idle", default=True))
        self._card_layout.addWidget(self._auto_idle_cb)

    def _page_character_parent(self):
        self._ph("请在下方选择「接口设置」或「立绘设置」")

    def _page_character_api(self):
        self._ph("角色 API 接口将在后续版本中支持")

    def _page_character_sprites(self):
        self._sec("立绘设置")

        self._char_list = QTreeWidget()
        self._char_list.setHeaderHidden(True)
        self._char_list.setStyleSheet(
            "QTreeWidget { border: 1px solid #e2e6ed; border-radius: 8px; padding: 4px;"
            "font-size: 13px; max-height: 120px; }"
            "QTreeWidget::item { padding: 6px 10px; border-radius: 4px; }"
            "QTreeWidget::item:selected { background: #fce4ec; color: #e94560; }"
        )
        for n in self._characters:
            item = QTreeWidgetItem([n])
            self._char_list.addTopLevelItem(item)
            if n == self._current_char:
                self._char_list.setCurrentItem(item)
        self._card_layout.addWidget(self._char_list)

        hint = QLabel("选择后点击「应用」切换角色")
        hint.setStyleSheet("color: #999; font-size: 11px;")
        self._card_layout.addWidget(hint)

    def _page_ai(self):
        self._ph("AI 对话功能将在后续版本中支持")

    def _page_tts(self):
        self._ph("语音合成（TTS）将在后续版本中支持\n音色训练计划中")

    def _page_asr(self):
        self._ph("语音输入（ASR）将在后续版本中支持")

    def _page_about(self):
        about_text = QLabel(
            "Moepet - 萌系桌面宠物\n"
            "基于 PySide6 的桌面宠物应用\n\n"
            "支持多角色切换、Galgame 风格对话框、\n"
            "立绘动画演出、系统托盘等功能。\n\n"
            "GitHub: zhuge-Tom/moepet"
        )
        about_text.setStyleSheet("color: #555; font-size: 13px; padding: 16px;")
        about_text.setAlignment(Qt.AlignCenter)
        self._card_layout.addWidget(about_text)

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

        s_slider = safe(getattr(self, "_scale_slider", None))
        s_top = safe(getattr(self, "_always_top_cb", None))
        s_click = safe(getattr(self, "_click_combo", None))
        s_idle = safe(getattr(self, "_auto_idle_cb", None))
        s_chars = safe(getattr(self, "_char_list", None))

        curr = self._current_char
        if s_chars and s_chars.currentItem():
            curr = s_chars.currentItem().text(0)

        return {
            "current_character": curr,
            "window": {"scale": s_slider.value() / 100.0 if s_slider else 1.0},
            "behavior": {
                "click_action": s_click.currentData() if s_click else "switch_sprite",
                "always_on_top": s_top.isChecked() if s_top else True,
                "auto_idle": s_idle.isChecked() if s_idle else True,
            },
        }

    def get_new_character(self) -> str | None:
        cl = getattr(self, "_char_list", None)
        if not cl:
            return None
        i = cl.currentItem()
        return i.text(0) if i and i.text(0) != self._current_char else None

    def _on_apply(self):
        v = self._collect_settings()
        # 写入 config
        for section in ("window", "behavior"):
            if section in v and isinstance(v[section], dict):
                for k, val in v[section].items():
                    self.config.set(section, k, val)
        if "current_character" in v:
            self.config.set("current_character", v["current_character"])
        self.config.save()
        self.apply_clicked.emit(v)

    def _on_scale_slider(self, v):
        self._scale_label.setText(f"{v}%")
        self.scale_changed.emit(v / 100.0)

    def _on_ok(self):
        self._on_apply()
        self.accept()
