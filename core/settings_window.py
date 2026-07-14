"""
设置窗口 - 树形导航：角色设置下含接口/立绘子项
收拢→按钮上移 + 搜索变图标 + 右侧展开
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QSlider, QCheckBox, QComboBox, QPushButton,
    QScrollArea, QFrame, QLineEdit, QTreeWidget, QTreeWidgetItem
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QFont, QIcon, QPixmap

# 树形导航：(emoji, 文字, key, 启用, 子项列表)
NAV_TREE = [
    ("⚙", "通用设置", "general", True, []),
    ("🤖", "AI模型", "ai_model", False, []),
    ("🔊", "语音合成", "tts", False, []),
    ("🎤", "语音输入", "asr", False, []),
    ("🎭", "角色设置", "character", True, [
        ("接口设置", "character_api"),
        ("立绘设置", "character_sprites"),
    ]),
]

NAV_WIDE = 160
NAV_NARROW = 48
ANIM_MS = 220
ROW_H = 36


class SettingsWindow(QDialog):
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
        # 默认选中立绘设置
        self._select_key("character_sprites")

    # ═══════════════════════════════════
    # 主布局
    # ═══════════════════════════════════

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.nav_frame = self._build_nav()
        root.addWidget(self.nav_frame)

        self.right_area = self._build_right()
        root.addWidget(self.right_area, 1)

    # ═══════════════════════════════════
    # 左侧导航
    # ═══════════════════════════════════

    def _build_nav(self):
        frame = QFrame()
        frame.setMinimumWidth(NAV_WIDE)
        frame.setMaximumWidth(NAV_WIDE)
        frame.setStyleSheet("QFrame{background:#e6e9ef;border-right:1px solid #d3d7de;}")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 顶行 ──
        top = QHBoxLayout()
        top.setContentsMargins(4, 6, 6, 4)
        top.setSpacing(4)

        self.collapse_btn = QPushButton("☰")
        self.collapse_btn.setFixedSize(30, 28)
        self.collapse_btn.setToolTip("收起导航")
        self.collapse_btn.setStyleSheet("QPushButton{background:transparent;border:none;font-size:16px;color:#555;border-radius:4px}QPushButton:hover{background:rgba(0,0,0,0.08)}")
        self.collapse_btn.clicked.connect(self._toggle_nav)
        top.addWidget(self.collapse_btn)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("查找设置...")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setFixedHeight(28)
        self.search_box.setStyleSheet("QLineEdit{border:1px solid #d3d7de;border-radius:6px;padding:2px 6px;font-size:11px;background:#fff}QLineEdit:focus{border-color:#3b82f6}")
        self.search_box.textChanged.connect(self._on_search)
        top.addWidget(self.search_box, 1)

        self.search_icon_btn = QPushButton("🔍")
        self.search_icon_btn.setFixedSize(30, 28)
        self.search_icon_btn.setToolTip("搜索")
        self.search_icon_btn.setStyleSheet("QPushButton{background:transparent;border:none;font-size:13px;border-radius:4px}QPushButton:hover{background:rgba(0,0,0,0.08)}")
        self.search_icon_btn.clicked.connect(self._expand_nav)
        self.search_icon_btn.hide()
        top.addWidget(self.search_icon_btn)

        layout.addLayout(top)

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
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings{border-image:none;image:none;}
            QTreeWidget::branch:open:has-children:!has-siblings,
            QTreeWidget::branch:open:has-children:has-siblings{border-image:none;image:none;}
        """)

        for emoji, text, key, enabled, children in NAV_TREE:
            parent = QTreeWidgetItem([f" {text}"])
            parent.setData(0, Qt.UserRole, key)
            parent.setIcon(0, self._icon(emoji))
            if not enabled:
                parent.setFlags(parent.flags() & ~Qt.ItemIsEnabled)
                parent.setForeground(0, Qt.gray)
            self._tree.addTopLevelItem(parent)

            for child_text, child_key in children:
                child = QTreeWidgetItem([f"  {child_text}"])
                child.setData(0, Qt.UserRole, child_key)
                parent.addChild(child)

        self._tree.currentItemChanged.connect(self._on_tree_changed)

        # 计算固定高度
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
        # 所有项只显示图标
        for i in range(self._tree.topLevelItemCount()):
            self._strip_text(self._tree.topLevelItem(i))
        self.collapse_btn.setText("▶"); self.collapse_btn.setFixedSize(24, 24)
        self.search_box.hide(); self.search_icon_btn.show()

    def _do_expand(self):
        self._anim_nav_width(NAV_WIDE)
        for i, (emoji, text, key, enabled, children) in enumerate(NAV_TREE):
            parent = self._tree.topLevelItem(i)
            parent.setText(0, f" {text}")
            for j, (ct, ck) in enumerate(children):
                parent.child(j).setText(0, f"  {ct}")
        self.collapse_btn.setText("☰"); self.collapse_btn.setFixedSize(30, 28)
        self.search_icon_btn.hide(); self.search_box.show()

    def _strip_text(self, item):
        item.setText(0, "")
        for i in range(item.childCount()):
            self._strip_text(item.child(i))

    def _anim_nav_width(self, target):
        cur = self.nav_frame.width()
        for prop in (b"minimumWidth", b"maximumWidth"):
            a = QPropertyAnimation(self.nav_frame, prop)
            a.setDuration(ANIM_MS)
            a.setStartValue(cur)
            a.setEndValue(target)
            a.setEasingCurve(QEasingCurve.InOutCubic)
            a.start()

    def _on_search(self, text):
        def match(item):
            return not text.strip() or text.strip().lower() in item.text(0).lower()

        for i in range(self._tree.topLevelItemCount()):
            p = self._tree.topLevelItem(i)
            any_visible = False
            for j in range(p.childCount()):
                c = p.child(j)
                visible = match(c)
                c.setHidden(not visible)
                if visible: any_visible = True
            p.setHidden(not any_visible and not match(p))

    # ═══════════════════════════════════
    # 右侧
    # ═══════════════════════════════════

    def _build_right(self):
        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(20, 12, 20, 16)
        layout.setSpacing(10)

        self.page_title = QLabel("立绘设置")
        self.page_title.setStyleSheet("font-size:18px;font-weight:bold;color:#1e293b;")
        layout.addWidget(self.page_title, alignment=Qt.AlignLeft)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none}QScrollBar:vertical{width:6px;background:transparent;border-radius:3px}QScrollBar::handle:vertical{background:#c8ccd4;border-radius:3px;min-height:30px}QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0}")

        self.card = QFrame()
        self.card.setStyleSheet("QFrame{background:#fff;border-radius:14px;border:1px solid #e2e6ed;}")
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(24, 20, 24, 20)
        self.card_layout.setSpacing(14)

        scroll.setWidget(self.card)
        layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout(); btn_row.addStretch()
        for text, slot, pri in [("应用", self._on_apply, False), ("确定", self._on_ok, True), ("取消", self.reject, False)]:
            b = QPushButton(text)
            b.setStyleSheet("QPushButton{background:#3b82f6;color:#fff;border:none;border-radius:7px;padding:7px 22px;font-size:13px}QPushButton:hover{background:#2563eb}" if pri else "QPushButton{background:#fff;color:#444;border:1px solid #d3d7de;border-radius:7px;padding:7px 22px;font-size:13px}QPushButton:hover{background:#f5f6fa}")
            b.clicked.connect(slot); btn_row.addWidget(b)
        layout.addLayout(btn_row)
        return right

    # ═══════════════════════════════════
    # 页面切换
    # ═══════════════════════════════════

    def _on_tree_changed(self, cur, prev):
        if not cur: return
        key = cur.data(0, Qt.UserRole)
        self._switch_page(key)

    def _select_key(self, key):
        """选中指定 key 的节点"""
        def find(item):
            if item.data(0, Qt.UserRole) == key:
                self._tree.setCurrentItem(item)
                return True
            for i in range(item.childCount()):
                if find(item.child(i)): return True
            return False
        for i in range(self._tree.topLevelItemCount()):
            if find(self._tree.topLevelItem(i)): break

    def _switch_page(self, key):
        while self.card_layout.count():
            w = self.card_layout.takeAt(0)
            if w.widget(): w.widget().deleteLater()

        # 找标题
        for _, text, k, _, children in NAV_TREE:
            if k == key: self.page_title.setText(text); break
            for ct, ck in children:
                if ck == key: self.page_title.setText(ct); break

        builders = {
            "general": self._general,
            "ai_model": self._ai, "tts": self._tts, "asr": self._asr,
            "character": self._character_parent,
            "character_api": self._character_api,
            "character_sprites": self._character_sprites,
        }
        builders[key]()
        self.card_layout.addStretch()

    # ═══════════════════════════════════
    # 页面
    # ═══════════════════════════════════

    def _general(self):
        self._sec("窗口"); self.always_top_cb = QCheckBox("始终置顶"); self.card_layout.addWidget(self.always_top_cb)
        self._sec("缩放")
        row = QHBoxLayout()
        self.size_slider = QSlider(Qt.Horizontal); self.size_slider.setRange(20,200)
        self.size_slider.setStyleSheet("QSlider::groove:horizontal{height:4px;background:#e2e6ed;border-radius:2px}QSlider::handle:horizontal{width:14px;height:14px;margin:-5px 0;background:#3b82f6;border-radius:7px}")
        self.size_label = QLabel("100%"); self.size_label.setFixedWidth(42); self.size_label.setStyleSheet("color:#3b82f6;font-weight:bold;font-size:13px")
        self.size_slider.valueChanged.connect(lambda v: self.size_label.setText(f"{v}%"))
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

    def _character_parent(self):
        """点击'角色设置'父节点 → 显示占位"""
        self._ph("请在下方子项中选择「接口设置」或「立绘设置」")

    def _character_api(self):
        self._ph("角色 API 接口将在后续版本中支持")

    def _character_sprites(self):
        self._sec("立绘设置")
        self.char_list = QTreeWidget()
        self.char_list.setHeaderHidden(True)
        self.char_list.setStyleSheet("QTreeWidget{border:1px solid #e2e6ed;border-radius:8px;padding:4px;font-size:13px;max-height:120px}QTreeWidget::item{padding:6px 10px;border-radius:4px}QTreeWidget::item:selected{background:#ecf3fd;color:#3b82f6}")
        for n in self.characters:
            item = QTreeWidgetItem([n])
            self.char_list.addTopLevelItem(item)
            if n == self._current_char:
                self.char_list.setCurrentItem(item)
        self.card_layout.addWidget(self.char_list)
        t = QLabel("选择后点击「应用」切换角色"); t.setStyleSheet("color:#999;font-size:11px"); self.card_layout.addWidget(t)

    def _sec(self,t):
        l=QLabel(t); l.setStyleSheet("font-weight:bold;font-size:13px;color:#64748b;margin-top:2px"); self.card_layout.addWidget(l)
    def _ph(self,t):
        l=QLabel(t); l.setStyleSheet("color:#94a3b8;font-size:13px;padding:20px"); l.setAlignment(Qt.AlignCenter); self.card_layout.addWidget(l)

    # ═══════════════════════════════════
    # 数据
    # ═══════════════════════════════════

    def _collect(self):
        s=getattr(self,'size_slider',None); t=getattr(self,'always_top_cb',None)
        c=getattr(self,'click_combo',None); a=getattr(self,'auto_idle_cb',None)
        cl=getattr(self,'char_list',None)
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
    def _on_ok(self):
        self._on_apply(); self.accept()
