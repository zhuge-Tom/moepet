"""
设置窗口 - 双折叠按钮实现上移动画 + 搜索左移
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QSlider, QCheckBox, QComboBox, QPushButton,
    QScrollArea, QFrame, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QSizePolicy
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtGui import QPainter, QFont, QIcon, QPixmap

NAV_TREE = [
    ("⚙", "通用设置", "general", True, []),
    ("🤖", "AI模型", "ai_model", False, []),
    ("🔊", "语音合成", "tts", False, []),
    ("🎤", "语音输入", "asr", False, []),
    ("🎭", "角色设置", "character", True, [
        ("🔌", "接口设置", "character_api"),
        ("🖼️", "立绘设置", "character_sprites"),
    ]),
]
NAV_WIDE = 160
NAV_NARROW = 48
ANIM_MS = 220
ROW_H = 36


class SettingsWindow(QDialog):
    scale_changed = Signal(float)
    apply_clicked = Signal()

    def __init__(self, config, characters, current_char, parent=None):
        super().__init__(parent)
        self.config = config
        self.characters = characters
        self._current_char = current_char
        self._collapsed = False

        self.setWindowTitle("Moepet 设置")
        self.setMinimumSize(480, 420)
        self.resize(640, 480)
        self.setStyleSheet("QDialog{background:#f0f2f5;}")

        self._setup_ui()
        self._tree.setCurrentItem(self._tree.topLevelItem(0))

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.nav_frame = self._build_nav()
        root.addWidget(self.nav_frame)
        root.addWidget(self._build_right(), 1)

    # ═══════════════════════════════════
    # 导航栏
    # ═══════════════════════════════════

    def _build_nav(self):
        frame = QFrame()
        frame.setMinimumWidth(NAV_WIDE)
        frame.setMaximumWidth(NAV_WIDE)
        frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        frame.setStyleSheet("QFrame{background:#e6e9ef;border-right:1px solid #d3d7de;}")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 描述区行（含隐藏的折叠按钮，收拢后才显示） ──
        self._desc_row = QHBoxLayout()
        self._desc_row.setContentsMargins(6, 6, 6, 2)
        self._desc_row.setSpacing(4)

        self._desc_label = QLabel("Moepet")
        self._desc_label.setStyleSheet(
            "font-size:14px;font-weight:bold;color:#2c3e50;background:transparent;")
        self._desc_row.addWidget(self._desc_label, 1)

        # 折叠按钮A：在描述行，初始隐藏，收拢后显示
        self._collapse_top = QPushButton("▶")
        self._collapse_top.setFixedSize(NAV_NARROW - 8, 24)
        self._collapse_top.setToolTip("展开导航")
        self._collapse_top.setStyleSheet(
            "QPushButton{background:transparent;border:none;font-size:14px;"
            "color:#555;border-radius:4px}QPushButton:hover{background:rgba(0,0,0,0.08)}")
        self._collapse_top.clicked.connect(self._expand_nav)
        self._collapse_top.hide()
        self._desc_row.addWidget(self._collapse_top)

        layout.addLayout(self._desc_row)

        # ── 折叠+搜索行 ──
        self._tool_row = QHBoxLayout()
        self._tool_row.setContentsMargins(4, 2, 6, 4)
        self._tool_row.setSpacing(4)

        # 折叠按钮B：在搜索行，初始显示，收拢后隐藏
        self._collapse_side = QPushButton("☰")
        self._collapse_side.setFixedSize(30, 28)
        self._collapse_side.setToolTip("收起导航")
        self._collapse_side.setStyleSheet(
            "QPushButton{background:transparent;border:none;font-size:16px;"
            "color:#555;border-radius:4px}QPushButton:hover{background:rgba(0,0,0,0.08)}")
        self._collapse_side.clicked.connect(self._toggle_nav)
        self._tool_row.addWidget(self._collapse_side)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("查找设置...")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setFixedHeight(28)
        self.search_box.setStyleSheet(
            "QLineEdit{border:1px solid #d3d7de;border-radius:6px;padding:2px 6px;"
            "font-size:11px;background:#fff}QLineEdit:focus{border-color:#3b82f6}")
        self.search_box.textChanged.connect(self._on_search)
        self._tool_row.addWidget(self.search_box, 1)

        # 搜索图标（收拢后显示在搜索行最左）
        self._search_icon = QPushButton("🔍")
        self._search_icon.setFixedSize(30, 28)
        self._search_icon.setToolTip("搜索")
        self._search_icon.setStyleSheet(
            "QPushButton{background:transparent;border:none;font-size:13px;"
            "border-radius:4px}QPushButton:hover{background:rgba(0,0,0,0.08)}")
        self._search_icon.clicked.connect(self._expand_nav)
        self._search_icon.hide()
        self._tool_row.addWidget(self._search_icon)

        layout.addLayout(self._tool_row)

        # ── 树形导航 ──
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(16)
        self._tree.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._tree.verticalScrollBar().setEnabled(False)
        self._tree.setAnimated(True)
        self._tree.setStyleSheet("""
            QTreeWidget{background:transparent;border:none;outline:none;font-size:13px;}
            QTreeWidget::item{padding:7px 6px;border-radius:6px;color:#555;}
            QTreeWidget::item:selected{background:#fff;color:#3b82f6;font-weight:bold;}
            QTreeWidget::item:hover:!selected{background:rgba(255,255,255,0.4);}
        """)

        for emoji, text, key, enabled, children in NAV_TREE:
            p = QTreeWidgetItem([f" {text}"])
            p.setData(0, Qt.UserRole, key)
            p.setIcon(0, self._icon(emoji))
            if not enabled:
                p.setFlags(p.flags() & ~Qt.ItemIsEnabled)
                p.setForeground(0, Qt.gray)
            self._tree.addTopLevelItem(p)
            # 初始展开状态：创建子项
            for ct_emoji, ct, ck in children:
                c = QTreeWidgetItem([f"{ct}"])
                c.setData(0, Qt.UserRole, ck)
                c.setIcon(0, self._icon(ct_emoji))
                p.addChild(c)
            # 保存子项数据供折叠/展开时重建
            if children:
                p.setData(0, Qt.UserRole + 1, children)

        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.currentItemChanged.connect(self._on_tree_changed)
        # 折叠后树太窄，viewport 事件捕获兜底
        self._tree.viewport().installEventFilter(self)
        total_rows = sum(1 + len(ch) for _, _, _, _, ch in NAV_TREE)
        self._tree.setFixedHeight(ROW_H * total_rows + 8)
        layout.addWidget(self._tree)
        layout.addStretch()
        return frame

    def _icon(self, emoji):
        pm = QPixmap(20, 20); pm.fill(Qt.transparent)
        p = QPainter(pm); f = QFont(); f.setPixelSize(16); p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignCenter, emoji); p.end()
        return QIcon(pm)

    # ═══════════════════════════════════
    # 折叠/展开
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
        # 移除所有子项（折叠后用弹菜单）
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
        # 恢复所有子项
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
        """viewport 点击兜底：折叠后 itemClicked 可能不触发"""
        from PySide6.QtCore import QEvent
        if obj is self._tree.viewport() and event.type() == QEvent.MouseButtonRelease:
            item = self._tree.itemAt(event.pos())
            if item:
                self._on_item_clicked(item, 0)
                return True
        return super().eventFilter(obj, event)

    def _anim_nav_width(self, target):
        cur = self.nav_frame.width()
        self._anims = []
        for prop in (b"minimumWidth", b"maximumWidth"):
            a = QPropertyAnimation(self.nav_frame, prop)
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
                if v: any_vis = True
            p.setHidden(not any_vis and not (
                not text.strip() or text.strip().lower() in p.text(0).lower()))

    # ═══════════════════════════════════
    # 右侧 + 页面（不变）
    # ═══════════════════════════════════

    def _on_tree_changed(self, cur, prev):
        if not cur: return
        self._switch_page(cur.data(0, Qt.UserRole))

    def _on_item_clicked(self, item, col):
        """单击处理：有子项则弹菜单，否则切换页面"""
        children = item.data(0, Qt.UserRole + 1)
        if children:
            self._popup_children_menu(item, children)
        else:
            self._switch_page(item.data(0, Qt.UserRole))

    def _popup_children_menu(self, item, children):
        """弹出子项菜单"""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction
        menu = QMenu(self)
        for emoji, text, key in children:
            action = QAction(f"{emoji}  {text}", self)
            action.setData(key)
            action.triggered.connect(lambda checked, k=key: self._switch_page(k))
            menu.addAction(action)
        # 在 item 下方弹出
        rect = self._tree.visualItemRect(item)
        pos = self._tree.viewport().mapToGlobal(rect.bottomLeft())
        menu.exec(pos)
    def _switch_page(self, key):
        while self.card_layout.count():
            w = self.card_layout.takeAt(0)
            if w.widget(): w.widget().deleteLater()
        for _, text, k, _, children in NAV_TREE:
            if k == key: self.page_title.setText(text); break
        {"general": self._general, "ai_model": self._ai, "tts": self._tts,
         "asr": self._asr, "character": self._character_parent,
         "character_api": self._character_api,
         "character_sprites": self._character_sprites}[key]()
        self.card_layout.addStretch()

    def _build_right(self):
        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(20, 12, 20, 16)
        layout.setSpacing(10)
        self.page_title = QLabel("通用设置")
        self.page_title.setStyleSheet("font-size:18px;font-weight:bold;color:#1e293b;")
        layout.addWidget(self.page_title, alignment=Qt.AlignLeft)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none}QScrollBar:vertical{width:6px;background:transparent;border-radius:3px}QScrollBar::handle:vertical{background:#c8ccd4;border-radius:3px;min-height:30px}QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0}")
        self.card = QFrame()
        self.card.setStyleSheet("QFrame{background:#fff;border-radius:14px;border:1px solid #e2e6ed;}")
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(24, 20, 24, 20)
        self.card_layout.setSpacing(14)
        scroll.setWidget(self.card); layout.addWidget(scroll, 1)
        btn_row = QHBoxLayout(); btn_row.addStretch()
        for text, slot, pri in [("应用", self._on_apply, False), ("确定", self._on_ok, True), ("取消", self.reject, False)]:
            b = QPushButton(text)
            b.setStyleSheet("QPushButton{background:#3b82f6;color:#fff;border:none;border-radius:7px;padding:7px 22px;font-size:13px}QPushButton:hover{background:#2563eb}" if pri else "QPushButton{background:#fff;color:#444;border:1px solid #d3d7de;border-radius:7px;padding:7px 22px;font-size:13px}QPushButton:hover{background:#f5f6fa}")
            b.clicked.connect(slot); btn_row.addWidget(b)
        layout.addLayout(btn_row)
        return right

    def _general(self):
        self._sec("窗口"); self.always_top_cb = QCheckBox("始终置顶"); self.card_layout.addWidget(self.always_top_cb)
        self._sec("缩放")
        row = QHBoxLayout()
        self.size_slider = QSlider(Qt.Horizontal); self.size_slider.setRange(20,200)
        self.size_slider.setStyleSheet("QSlider::groove:horizontal{height:4px;background:#e2e6ed;border-radius:2px}QSlider::handle:horizontal{width:14px;height:14px;margin:-5px 0;background:#3b82f6;border-radius:7px}")
        self.size_label = QLabel("100%"); self.size_label.setFixedWidth(42); self.size_label.setStyleSheet("color:#3b82f6;font-weight:bold;font-size:13px")
        self.size_slider.valueChanged.connect(self._on_scale_slider)
        row.addWidget(self.size_slider,1); row.addWidget(self.size_label); self.card_layout.addLayout(row)
        self._sec("行为")
        self.click_combo = QComboBox()
        self.click_combo.addItem("切换下一张立绘","switch_sprite"); self.click_combo.addItem("弹跳一下","bounce"); self.click_combo.addItem("无反应","none")
        self.click_combo.setStyleSheet("QComboBox{border:1px solid #d3d7de;border-radius:6px;padding:6px 10px;font-size:13px}")
        self.card_layout.addWidget(self.click_combo)
        self.auto_idle_cb = QCheckBox("自动待机动画"); self.card_layout.addWidget(self.auto_idle_cb)
        self._load_general()

    def _load_general(self):
        self.always_top_cb.setChecked(self.config.get("behavior","always_on_top",default=True))
        self.size_slider.setValue(int(self.config.get("window","scale",default=1.0)*100))
        a = self.config.get("behavior","click_action",default="switch_sprite")
        i = self.click_combo.findData(a)
        if i>=0: self.click_combo.setCurrentIndex(i)
        self.auto_idle_cb.setChecked(self.config.get("behavior","auto_idle",default=True))

    def _ai(self): self._ph("AI 对话功能将在后续版本中支持")
    def _tts(self): self._ph("语音合成（TTS）将在后续版本中支持\n音色训练计划中")
    def _asr(self): self._ph("语音输入（ASR）将在后续版本中支持")
    def _character_parent(self): self._ph("请在下方选择「接口设置」或「立绘设置」")
    def _character_api(self): self._ph("角色 API 接口将在后续版本中支持")

    def _character_sprites(self):
        self._sec("立绘设置")
        self.char_list = QTreeWidget()
        self.char_list.setHeaderHidden(True)
        self.char_list.setStyleSheet("QTreeWidget{border:1px solid #e2e6ed;border-radius:8px;padding:4px;font-size:13px;max-height:120px}QTreeWidget::item{padding:6px 10px;border-radius:4px}QTreeWidget::item:selected{background:#ecf3fd;color:#3b82f6}")
        for n in self.characters:
            item = QTreeWidgetItem([n]); self.char_list.addTopLevelItem(item)
            if n == self._current_char: self.char_list.setCurrentItem(item)
        self.card_layout.addWidget(self.char_list)
        t = QLabel("选择后点击「应用」切换角色"); t.setStyleSheet("color:#999;font-size:11px"); self.card_layout.addWidget(t)

    def _sec(self,t):
        l=QLabel(t); l.setStyleSheet("font-weight:bold;font-size:13px;color:#64748b;margin-top:2px"); self.card_layout.addWidget(l)
    def _ph(self,t):
        l=QLabel(t); l.setStyleSheet("color:#94a3b8;font-size:13px;padding:20px"); l.setAlignment(Qt.AlignCenter); self.card_layout.addWidget(l)

    def _collect(self):
        import shiboken6 as sb
        def safe(obj, default=None):
            if obj is None:
                return default
            try:
                if not sb.isValid(obj):
                    return default
            except:
                return default
            return obj

        s = safe(getattr(self, 'size_slider', None))
        t = safe(getattr(self, 'always_top_cb', None))
        c = safe(getattr(self, 'click_combo', None))
        a = safe(getattr(self, 'auto_idle_cb', None))
        cl = safe(getattr(self, 'char_list', None))
        curr = self._current_char
        if cl and cl.currentItem():
            curr = cl.currentItem().text(0)
        return {"current_character":curr,
                "window":{"scale":s.value()/100.0 if s else 1.0},
                "behavior":{"click_action":c.currentData() if c else "switch_sprite",
                            "always_on_top":t.isChecked() if t else True,
                            "auto_idle":a.isChecked() if a else True}}

    def get_new_character(self):
        cl=getattr(self,'char_list',None)
        if not cl: return None
        i=cl.currentItem()
        return i.text(0) if i and i.text(0)!=self._current_char else None

    def _on_apply(self):
        v=self._collect()
        for kp,ud in [(("window",),v["window"]),(("behavior",),v["behavior"])]:
            t=self.config.data
            for k in kp: t=t.setdefault(k,{})
            t.update(ud)
        self.config.save()
        self.apply_clicked.emit()

    def _on_scale_slider(self, v):
        self.size_label.setText(f"{v}%")
        self.scale_changed.emit(v / 100.0)

    def _on_ok(self):
        self._on_apply(); self.accept()
