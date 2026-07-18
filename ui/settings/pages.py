"""Small independent settings pages.

Pages are intentionally pure widgets.  The settings window owns navigation and
form persistence while individual pages own their own presentation tree.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from ui.settings_components import ServiceStatusCard
from ui.settings.service_status import vision_ready


def _page_layout() -> tuple[QWidget, QVBoxLayout]:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(28, 24, 28, 28)
    layout.setSpacing(16)
    return page, layout


def _section(layout: QVBoxLayout, title: str) -> None:
    label = QLabel(title)
    label.setStyleSheet("font-weight: bold; font-size: 14px; color: #475569;")
    layout.addWidget(label)


def _hint(layout: QVBoxLayout, text: str) -> None:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("color: #94a3b8; font-size: 11px;")
    layout.addWidget(label)


def _line_edit(placeholder: str, password: bool = False) -> QLineEdit:
    field = QLineEdit()
    field.setPlaceholderText(placeholder)
    field.setFixedHeight(30)
    if password:
        field.setEchoMode(QLineEdit.Password)
    field.setStyleSheet(
        "QLineEdit { border: 1px solid #d3d7de; border-radius: 6px; padding: 4px 10px; font-size: 13px; }"
        "QLineEdit:focus { border-color: #e94560; }")
    return field


def _row(layout: QVBoxLayout, label: str, widget: QWidget) -> None:
    row = QHBoxLayout()
    row.setSpacing(16)
    text = QLabel(label)
    text.setStyleSheet("font-size: 13px; color: #2c3e50;")
    row.addWidget(text)
    row.addWidget(widget, 1)
    layout.addLayout(row)


def make_screen_page(config, add_probe) -> tuple[QWidget, dict[str, QWidget]]:
    page, layout = _page_layout()
    _hint(layout, "手动识别仅在快捷键或聊天明确请求时截图；主动观察需要单独授权。")
    _section(layout, "手动截图 OCR")
    keep = QCheckBox("保留截图（默认识别后删除）")
    keep.setChecked(config.get("screen_capture", "keep_captures", default=False))
    layout.addWidget(keep)
    hotkey = _line_edit("Ctrl+Alt+O")
    hotkey.setText(config.get("screen_capture", "hotkey", default="Ctrl+Alt+O"))
    _row(layout, "截图快捷键", hotkey)
    cloud_first = QCheckBox("优先使用视觉模型，失败时本地 OCR")
    cloud_first.setChecked(config.get("screen_capture", "cloud_first", default=True))
    layout.addWidget(cloud_first)

    _section(layout, "随机主动观察（可选）")
    auto_observe = QCheckBox("允许角色在随机间隔内观察屏幕并自然回应")
    auto_observe.setChecked(config.get("screen_capture", "auto_observe", default=False))
    layout.addWidget(auto_observe)
    fields = {"screen_keep": keep, "screen_hotkey": hotkey, "screen_cloud_first": cloud_first,
              "screen_auto_observe": auto_observe}
    for name, title, maximum, default in (
        ("screen_observe_min", "最短间隔", 120, 300),
        ("screen_observe_max", "最长间隔", 240, 900),
        ("screen_observe_cooldown", "回应冷却", 240, 600),
    ):
        spin = QSpinBox()
        spin.setRange(1, maximum)
        spin.setSuffix(" 分钟")
        setting = {"screen_observe_min": "observe_min_interval", "screen_observe_max": "observe_max_interval",
                   "screen_observe_cooldown": "observe_cooldown"}[name]
        spin.setValue(max(1, int(config.get("screen_capture", setting, default=default)) // 60))
        _row(layout, title, spin)
        fields[name] = spin
    _hint(layout, "主动观察默认关闭；需要图像理解可用，云端服务还需确认上传授权。")
    add_probe(layout, "ocr", "测试本地 OCR")
    layout.addStretch()
    return page, fields


def make_vision_page(config, add_probe) -> tuple[QWidget, dict[str, QWidget]]:
    page, layout = _page_layout()
    card = ServiceStatusCard("图像理解", "用于手动识图和已授权的主动屏幕观察。")
    card.set_state(vision_ready(config))
    layout.addWidget(card)
    _section(layout, "服务连接")
    enabled = QCheckBox("允许发送截图到已配置的视觉服务")
    enabled.setChecked(config.get("vision", "enabled", default=False))
    layout.addWidget(enabled)
    url = _line_edit("本地 Ollama 或云端 OpenAI 兼容地址")
    url.setText(config.get("vision", "base_url", default=""))
    _row(layout, "Base URL", url)
    model = _line_edit("视觉模型名称")
    model.setText(config.get("vision", "model", default=""))
    _row(layout, "模型", model)
    key = _line_edit("可选 API Key", password=True)
    key.setText(config.get_secret("vision") or config.get("vision", "api_key", default=""))
    _row(layout, "API Key", key)
    _section(layout, "隐私授权")
    allow_cloud = QCheckBox("我同意将主动截图上传到云端视觉服务")
    allow_cloud.setChecked(config.get("vision", "allow_cloud", default=False))
    layout.addWidget(allow_cloud)
    _hint(layout, "本地地址无需上传授权；云端地址必须勾选授权才会收到截图。")
    add_probe(layout, "vision", "测试图像理解服务")
    layout.addStretch()
    return page, {"vision_status_card": card, "vision_enabled": enabled, "vision_url": url,
                  "vision_model": model, "vision_key": key, "vision_allow_cloud": allow_cloud}


def make_about_page() -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(28, 24, 28, 28)
    layout.setSpacing(16)
    about = QLabel(
        "Moepet - 萌系桌面宠物\n"
        "基于 PySide6 的角色桌面伴侣\n\n"
        "支持多角色切换、AI 对话、Galgame 风格对话框、\n"
        "立绘动画演出、按住说话、屏幕理解与系统托盘。\n\n"
        "GitHub: zhuge-Tom/moepet"
    )
    about.setStyleSheet("color: #475569; font-size: 13px; padding: 16px;")
    about.setAlignment(Qt.AlignCenter)
    layout.addWidget(about)
    layout.addStretch()
    return page


def make_character_parent_page() -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(28, 24, 28, 28)
    hint = QLabel("请从左侧子项管理角色接口、立绘和资料库。")
    hint.setAlignment(Qt.AlignCenter)
    hint.setStyleSheet("color: #94a3b8; font-size: 13px; padding: 20px;")
    layout.addWidget(hint)
    layout.addStretch()
    return page
