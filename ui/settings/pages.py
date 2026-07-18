"""Small independent settings pages.

Pages are intentionally pure widgets.  The settings window owns navigation and
form persistence while individual pages own their own presentation tree.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
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


def _field_row(layout: QVBoxLayout, label: str, widget: QWidget) -> QWidget:
    """A hideable label/control row for provider-specific form fields."""
    container = QWidget()
    row = QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(16)
    text = QLabel(label)
    text.setStyleSheet("font-size: 13px; color: #2c3e50;")
    row.addWidget(text)
    row.addWidget(widget, 1)
    layout.addWidget(container)
    return container


def make_tts_page(config, add_probe) -> tuple[QWidget, dict[str, QWidget], dict[str, QWidget]]:
    page, layout = _page_layout()
    card = ServiceStatusCard("语音输出", "回复可由本地 CosyVoice 或兼容云端 TTS 朗读。")
    layout.addWidget(card)
    enabled = QCheckBox("LLM 回复后自动朗读")
    enabled.setChecked(config.get("tts", "enabled", default=False))
    layout.addWidget(enabled)
    provider = QComboBox()
    provider.addItem("本地 CosyVoice（使用角色授权参考音频）", "local")
    provider.addItem("云端 OpenAI 兼容 TTS API", "cloud")
    provider.setCurrentIndex(max(provider.findData(config.get("tts", "provider", default="local")), 0))
    _row(layout, "语音后端", provider)

    _section(layout, "本地语音")
    model_path = _line_edit("用户下载的 CosyVoice 模型目录")
    model_path.setText(config.get("tts", "model_path", default=""))
    local_row = _field_row(layout, "模型目录", model_path)
    speed = QSpinBox()
    speed.setRange(50, 200)
    speed.setSuffix(" %")
    speed.setValue(int(config.get("tts", "speed", default=1.0) * 100))
    _row(layout, "语速", speed)
    auto_play = QCheckBox("生成后自动播放语音")
    auto_play.setChecked(config.get("tts", "auto_play", default=True))
    layout.addWidget(auto_play)

    _section(layout, "云端 TTS API")
    api_url = _line_edit("https://api.example.com/v1/audio/speech")
    api_url.setText(config.get("tts", "base_url", default=""))
    api_key = _line_edit("sk-xxxx", password=True)
    api_key.setText(config.get_secret("tts") or config.get("tts", "api_key", default=""))
    api_model = _line_edit("tts-1 / 供应商模型名")
    api_model.setText(config.get("tts", "model", default="tts-1"))
    api_voice = _line_edit("alloy / 供应商音色名")
    api_voice.setText(config.get("tts", "voice", default="alloy"))
    cloud_rows = {
        "tts_api_url": _field_row(layout, "合成地址", api_url),
        "tts_api_key": _field_row(layout, "API Key", api_key),
        "tts_api_model": _field_row(layout, "模型", api_model),
        "tts_api_voice": _field_row(layout, "音色", api_voice),
    }
    add_probe(layout, "tts", "测试语音引擎")
    layout.addStretch()
    fields = {"tts_status_card": card, "tts_enabled": enabled, "tts_provider": provider,
              "tts_model": model_path, "tts_speed": speed, "tts_auto_play": auto_play,
              "tts_api_url": api_url, "tts_api_key": api_key, "tts_api_model": api_model,
              "tts_api_voice": api_voice}
    rows = {"tts_model": local_row, **cloud_rows}
    return page, fields, rows


def make_asr_page(config, add_probe) -> tuple[QWidget, dict[str, QWidget], dict[str, QWidget]]:
    page, layout = _page_layout()
    card = ServiceStatusCard("按住说话", "按住快捷键录音，松开后自动转写到对话。")
    layout.addWidget(card)
    enabled = QCheckBox("启用按键语音输入")
    enabled.setChecked(config.get("asr", "enabled", default=False))
    layout.addWidget(enabled)
    provider = QComboBox()
    provider.addItem("本地模型（不上传音频）", "local")
    provider.addItem("云端 OpenAI 兼容 ASR API", "cloud")
    provider.setCurrentIndex(max(provider.findData(config.get("asr", "provider", default="local")), 0))
    _row(layout, "识别后端", provider)

    _section(layout, "本地 faster-whisper")
    engine = QComboBox()
    engine.addItem("faster-whisper（本地运行，推荐）", "faster-whisper")
    model_path = _line_edit("用户下载的 faster-whisper 模型目录")
    model_path.setText(config.get("asr", "model_path", default=""))
    device = QComboBox()
    device.addItem("CPU（兼容性最好）", "cpu")
    device.addItem("CUDA GPU", "cuda")
    device.setCurrentIndex(max(device.findData(config.get("asr", "device", default="cpu")), 0))
    compute = QComboBox()
    compute.addItem("int8（速度与内存平衡）", "int8")
    compute.addItem("float16（GPU 推荐）", "float16")
    compute.addItem("float32（精度优先）", "float32")
    compute.setCurrentIndex(max(compute.findData(config.get("asr", "compute_type", default="int8")), 0))
    local_rows = {
        "asr_engine": _field_row(layout, "引擎", engine),
        "asr_model": _field_row(layout, "模型目录", model_path),
        "asr_device": _field_row(layout, "运行设备", device),
        "asr_compute": _field_row(layout, "计算精度", compute),
    }
    hotkey = _line_edit("Ctrl+Alt+Space")
    hotkey.setText(config.get("asr", "hotkey", default="Ctrl+Alt+Space"))
    _row(layout, "按住说话快捷键", hotkey)
    auto_send = QCheckBox("识别结束后自动发送到对话框")
    auto_send.setChecked(config.get("asr", "auto_send", default=True))
    layout.addWidget(auto_send)

    _section(layout, "云端识别 API")
    api_url = _line_edit("https://api.example.com/v1/audio/transcriptions")
    api_url.setText(config.get("asr", "base_url", default=""))
    api_key = _line_edit("sk-xxxx", password=True)
    api_key.setText(config.get_secret("asr") or config.get("asr", "api_key", default=""))
    api_model = _line_edit("whisper-1 / 供应商模型名")
    api_model.setText(config.get("asr", "model", default="whisper-1"))
    language = _line_edit("留空自动识别，例如 zh")
    language.setText(config.get("asr", "language", default=""))
    cloud_rows = {
        "asr_api_url": _field_row(layout, "转写地址", api_url),
        "asr_api_key": _field_row(layout, "API Key", api_key),
        "asr_api_model": _field_row(layout, "模型", api_model),
        "asr_api_language": _field_row(layout, "识别语言", language),
    }
    add_probe(layout, "asr", "测试当前识别后端")
    layout.addStretch()
    fields = {"asr_status_card": card, "asr_enabled": enabled, "asr_provider": provider,
              "asr_engine": engine, "asr_model": model_path, "asr_device": device,
              "asr_compute": compute, "asr_hotkey": hotkey, "asr_auto_send": auto_send,
              "asr_api_url": api_url, "asr_api_key": api_key, "asr_api_model": api_model,
              "asr_api_language": language}
    return page, fields, {**local_rows, **cloud_rows}


def make_ai_page(config) -> tuple[QWidget, dict[str, QWidget]]:
    page, layout = _page_layout()
    card = ServiceStatusCard("对话模型", "用于角色对话与主动观察后的自然回应。")
    layout.addWidget(card)
    _section(layout, "OpenAI 兼容 API")
    url = _line_edit("https://api.deepseek.com/v1")
    url.setText(config.get("llm", "base_url", default=""))
    _row(layout, "Base URL", url)
    key = _line_edit("sk-xxxx", password=True)
    key.setText(config.get_secret("llm") or config.get("llm", "api_key", default=""))
    _row(layout, "API Key", key)
    model = _line_edit("deepseek-chat / gpt-4o-mini / ...")
    model.setText(config.get("llm", "model", default=""))
    _row(layout, "模型", model)
    _hint(layout, "支持 DeepSeek、OpenAI、Ollama 等兼容 Chat Completions 的服务。")

    _section(layout, "高级设置")
    stream = QCheckBox("启用流式输出（逐字显示）")
    stream.setChecked(config.get("llm", "stream", default=True))
    layout.addWidget(stream)
    post_processing = _line_edit("例如 <think>.*?</think>")
    post_processing.setText(config.get("llm", "post_processing", default=""))
    _row(layout, "回复后处理（正则）", post_processing)
    ignore_format_error = QCheckBox("忽略格式错误")
    ignore_format_error.setChecked(config.get("llm", "ignore_format_error", default=True))
    layout.addWidget(ignore_format_error)

    test_button = QPushButton("测试连接")
    test_button.setFixedHeight(32)
    test_button.setStyleSheet(
        "QPushButton { background: #3498db; color: #fff; border: none; border-radius: 7px; padding: 7px 22px; }"
        "QPushButton:hover { background: #2980b9; }")
    layout.addWidget(test_button)
    status = QLabel("")
    status.setWordWrap(True)
    status.setStyleSheet("font-size: 12px; padding: 4px;")
    layout.addWidget(status)
    layout.addStretch()
    return page, {"ai_status_card": card, "ai_url": url, "ai_key": key, "ai_model": model,
                  "ai_stream_cb": stream, "ai_post": post_processing,
                  "ai_ignore_err_cb": ignore_format_error, "ai_test_button": test_button,
                  "test_status": status}


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
