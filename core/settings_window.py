"""
设置窗口 - 桌面宠物配置面板
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QSlider, QCheckBox, QComboBox, QPushButton,
    QGroupBox, QFormLayout, QWidget, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt


class SettingsWindow(QDialog):
    """设置对话框"""

    def __init__(self, config, characters: list[str], current_char: str, parent=None):
        super().__init__(parent)
        self.config = config
        self.characters = characters
        self._current_char = current_char
        self._settings_changed = False

        self.setWindowTitle("Moepet 设置")
        self.setMinimumWidth(420)
        self.setMinimumHeight(350)

        self._setup_ui()
        self._load_values()

    # ─── UI 搭建 ──────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 标签页
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_character_tab(), "🎭 角色")
        self.tabs.addTab(self._create_appearance_tab(), "✨ 外观")
        self.tabs.addTab(self._create_behavior_tab(), "🎮 行为")
        self.tabs.addTab(self._create_about_tab(), "ℹ️ 关于")
        layout.addWidget(self.tabs)

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        apply_btn = QPushButton("应用")
        apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(apply_btn)

        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self._on_ok)
        ok_btn.setDefault(True)
        btn_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    # ─── 角色标签页 ───────────────────────────

    def _create_character_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        label = QLabel("当前角色：")
        label.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(label)

        self.char_list = QListWidget()
        for name in self.characters:
            item = QListWidgetItem(name)
            self.char_list.addItem(item)
        layout.addWidget(self.char_list)

        tip = QLabel('选择角色后点击「应用」即可切换')
        tip.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(tip)

        return w

    # ─── 外观标签页 ───────────────────────────

    def _create_appearance_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        # 大小
        size_group = QGroupBox("角色大小")
        size_form = QFormLayout()
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(20, 200)  # 0.2x ~ 2.0x
        self.size_slider.setTickPosition(QSlider.TicksBelow)
        self.size_slider.setTickInterval(20)
        self.size_label = QLabel("100%")
        size_form.addRow("缩放比例：", self.size_slider)
        size_form.addRow("", self.size_label)
        size_group.setLayout(size_form)
        layout.addWidget(size_group)

        self.size_slider.valueChanged.connect(
            lambda v: self.size_label.setText(f"{v}%")
        )

        # 窗口选项
        win_group = QGroupBox("窗口选项")
        win_layout = QVBoxLayout()
        self.always_top_cb = QCheckBox("始终置顶")
        win_layout.addWidget(self.always_top_cb)
        win_group.setLayout(win_layout)
        layout.addWidget(win_group)

        layout.addStretch()
        return w

    # ─── 行为标签页 ───────────────────────────

    def _create_behavior_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        click_group = QGroupBox("点击行为")
        click_layout = QVBoxLayout()
        self.click_combo = QComboBox()
        self.click_combo.addItem("切换下一张立绘", "switch_sprite")
        self.click_combo.addItem("弹跳一下", "bounce")
        self.click_combo.addItem("无反应", "none")
        click_layout.addWidget(self.click_combo)
        click_group.setLayout(click_layout)
        layout.addWidget(click_group)

        idle_group = QGroupBox("待机")
        idle_layout = QVBoxLayout()
        self.auto_idle_cb = QCheckBox("自动待机动画（定时切换立绘）")
        idle_layout.addWidget(self.auto_idle_cb)
        idle_group.setLayout(idle_layout)
        layout.addWidget(idle_group)

        layout.addStretch()
        return w

    # ─── 关于标签页 ───────────────────────────

    def _create_about_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        title = QLabel("🐱 Moepet - 萌系桌面宠物")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        info = QLabel(
            "基于 PySide6 的动漫桌面宠物\n\n"
            "角色来源：星空列车与白的旅行\n"
            "角色：诺瓦 (nuowa)\n\n"
            "GitHub: github.com/zhuge-Tom/moepet"
        )
        info.setStyleSheet("font-size: 12px; color: #555;")
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addStretch()
        return w

    # ─── 数据读写 ─────────────────────────────

    def _load_values(self):
        """从配置加载当前值"""
        # 角色
        for i in range(self.char_list.count()):
            if self.char_list.item(i).text() == self._current_char:
                self.char_list.setCurrentRow(i)
                break

        # 外观
        scale = self.config.get("window", "scale", default=1.0)
        self.size_slider.setValue(int(scale * 100))
        self.always_top_cb.setChecked(
            self.config.get("behavior", "always_on_top", default=True)
        )

        # 行为
        click_action = self.config.get("behavior", "click_action", default="switch_sprite")
        idx = self.click_combo.findData(click_action)
        if idx >= 0:
            self.click_combo.setCurrentIndex(idx)
        self.auto_idle_cb.setChecked(
            self.config.get("behavior", "auto_idle", default=True)
        )

    def _collect_values(self) -> dict:
        """收集当前设置值"""
        return {
            "current_character": (
                self.char_list.currentItem().text()
                if self.char_list.currentItem() else self._current_char
            ),
            "window": {
                "scale": self.size_slider.value() / 100.0,
            },
            "behavior": {
                "click_action": self.click_combo.currentData(),
                "always_on_top": self.always_top_cb.isChecked(),
                "auto_idle": self.auto_idle_cb.isChecked(),
            }
        }

    def get_new_character(self) -> str | None:
        """返回用户选择的新角色（如果切换了）"""
        new = self.char_list.currentItem()
        if new and new.text() != self._current_char:
            return new.text()
        return None

    # ─── 按钮回调 ─────────────────────────────

    def _on_apply(self):
        """应用但不关闭"""
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
        self._settings_changed = True

    def _on_ok(self):
        """应用并关闭"""
        self._on_apply()
        self.accept()

    @property
    def settings_changed(self) -> bool:
        return self._settings_changed
