"""对话框窗口

Galgame 风格的浮动对话框，显示在立绘旁边。
支持逐字显示、历史记录、输入发送。
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTextEdit, QFrame,
    QScrollArea, QWidget,
)
from PySide6.QtCore import Qt, QTimer, Signal, QPoint, QEvent
from PySide6.QtGui import QMouseEvent, QTextCursor
from PySide6.QtGui import QFont

from ui.theme import DIALOG_QSS


class DialogWindow(QDialog):
    """Galgame 风格对话框"""

    text_submitted = Signal(str)
    voice_pressed = Signal()
    voice_released = Signal()
    screen_capture_requested = Signal()

    TYPING_INTERVAL = 40  # 逐字显示间隔（毫秒）

    def __init__(self, char_name: str = "???", parent=None):
        super().__init__(parent)
        self._char_name = char_name
        self._drag_pos = QPoint()
        self._full_text = ""
        self._typed_index = 0
        self._typing = False
        self._history: list[dict] = []
        self._is_streaming = False
        self._stream_buffer = ""
        self._scale_percent = 100
        self._voice_available = True
        self._voice_recording = False
        self._screen_busy = False

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(DIALOG_QSS)
        # Reserve room for capture, input, and send controls at high DPI.
        self.setMinimumSize(460, 240)
        self.resize(520, 280)

        self._typing_timer = QTimer(self)
        self._typing_timer.setInterval(self.TYPING_INTERVAL)
        self._typing_timer.timeout.connect(self._type_next_char)

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 外框容器
        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #1a1a2e; border: 2px solid #e94560; border-radius: 12px; }")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 12)
        frame_layout.setSpacing(0)

        # 角色名标签
        self._name_label = QLabel(self._char_name)
        self._name_label.setObjectName("name_label")
        self._name_label.setFixedHeight(28)
        frame_layout.addWidget(self._name_label)

        # 文本显示区
        self._text_display = QTextEdit()
        self._text_display.setObjectName("chat_display")
        self._text_display.setReadOnly(True)
        self._text_display.setMinimumHeight(120)
        self._text_display.setMaximumHeight(400)
        frame_layout.addWidget(self._text_display, 1)

        # 底部操作栏
        bottom = QHBoxLayout()
        bottom.setContentsMargins(12, 6, 12, 0)
        bottom.setSpacing(8)

        self._input = QLineEdit()
        self._input.setObjectName("input_field")
        self._input.setPlaceholderText("说点什么...")
        self._input.setFixedHeight(32)
        self._input.setMinimumWidth(160)
        self._input.returnPressed.connect(self._on_submit)
        bottom.addWidget(self._input, 1)

        self._voice_btn = QPushButton("按住说话")
        self._voice_btn.setObjectName("voice_btn")
        self._voice_btn.setFixedHeight(32)
        self._voice_btn.setToolTip("按住录音，松开后转写")
        self._voice_btn.pressed.connect(self.voice_pressed)
        self._voice_btn.released.connect(self.voice_released)
        bottom.addWidget(self._voice_btn)

        self._screen_btn = QPushButton("识图")
        self._screen_btn.setObjectName("screen_btn")
        self._screen_btn.setFixedHeight(32)
        self._screen_btn.setToolTip("识别当前屏幕")
        self._screen_btn.clicked.connect(self.screen_capture_requested)
        bottom.addWidget(self._screen_btn)

        self._send_btn = QPushButton("发送")
        self._send_btn.setObjectName("send_btn")
        self._send_btn.setFixedSize(72, 32)
        self._send_btn.clicked.connect(self._on_submit)
        bottom.addWidget(self._send_btn)

        frame_layout.addLayout(bottom)
        root.addWidget(frame)

    # ─── 文本显示 ─────────────────────────────

    def display_text(self, text: str, role: str = "assistant"):
        """逐字显示文本"""
        if self._typing:
            self._typing_timer.stop()

        # 存入历史
        self._history.append({"role": role, "text": text})

        # 开始逐字显示
        self._full_text = text
        self._typed_index = 0
        self._typing = True
        self._text_display.clear()
        self._typing_timer.start()

    def display_instant(self, text: str, role: str = "user"):
        """立即显示文本（用户消息用）"""
        self._history.append({"role": role, "text": text})
        self._text_display.setText(text)

    # ─── 流式输入（LLM 用）────────────────────

    def start_stream(self):
        """开始流式接收，清空显示区并显示思考中"""
        if self._typing:
            self._typing_timer.stop()
            self._typing = False
        self._text_display.clear()
        self._stream_buffer = ""
        self._is_streaming = True

    def append_stream(self, text: str):
        """追加流式文本片段"""
        if not self._is_streaming:
            self.start_stream()
        self._stream_buffer += text
        self._text_display.insertPlainText(text)
        cursor = self._text_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._text_display.setTextCursor(cursor)

    def finish_stream(self, full_text: str = ""):
        """流式结束，保存历史"""
        self._is_streaming = False
        text = full_text or self._stream_buffer
        if text:
            # The service may remove model markup after the last stream chunk.
            # Replace the provisional display so UI, history, and TTS agree.
            if full_text and full_text != self._stream_buffer:
                self._text_display.setPlainText(full_text)
            self._history.append({"role": "assistant", "text": text})

    def _type_next_char(self):
        if self._typed_index < len(self._full_text):
            self._text_display.insertPlainText(self._full_text[self._typed_index])
            self._typed_index += 1
            # 自动滚动到底部
            cursor = self._text_display.textCursor()
            cursor.movePosition(QTextCursor.End)
            self._text_display.setTextCursor(cursor)
        else:
            self._typing_timer.stop()
            self._typing = False

    # ─── 输入处理 ─────────────────────────────

    def _on_submit(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self.display_instant(text, "user")
        self.text_submitted.emit(text)

    # ─── 外部接口 ─────────────────────────────

    def set_character_name(self, name: str):
        self._char_name = name
        self._name_label.setText(name)

    def set_typing_speed(self, milliseconds: int):
        """Update the typewriter delay without interrupting active output."""
        self._typing_timer.setInterval(max(1, milliseconds))

    def set_voice_available(self, available: bool) -> None:
        """Keep the microphone action discoverable without exposing a broken control."""
        self._voice_available = bool(available)
        if not self._voice_available:
            self._voice_recording = False
        self._voice_btn.setEnabled(available)
        self._sync_voice_button()

    def set_voice_recording(self, recording: bool) -> None:
        """Show the press-and-hold state while the recorder owns the microphone."""
        self._voice_recording = bool(recording) and self._voice_available
        self._sync_voice_button()

    def _sync_voice_button(self) -> None:
        self._voice_btn.setText("松开结束" if self._voice_recording else "按住说话")
        self._voice_btn.setProperty("recording", self._voice_recording)
        self._voice_btn.style().unpolish(self._voice_btn)
        self._voice_btn.style().polish(self._voice_btn)
        self._voice_btn.setToolTip(
            "松开后将开始转写" if self._voice_recording else (
                "按住录音，松开后转写" if self._voice_available
                else "请先在设置中启用并配置语音输入"))

    def set_screen_available(self, available: bool) -> None:
        """Manual screen capture remains useful with either vision or local OCR."""
        self._screen_btn.setEnabled(available)
        self._screen_btn.setToolTip(
            "识别当前屏幕" if available else "请先配置本地 OCR 或图像理解服务")

    def set_screen_busy(self, busy: bool) -> None:
        """Prevent duplicate captures while an image request is still active."""
        self._screen_busy = bool(busy)
        self._screen_btn.setEnabled(not self._screen_busy)
        self._screen_btn.setText("识图中..." if self._screen_busy else "识图")
        self._screen_btn.setToolTip("正在识别当前屏幕" if self._screen_busy else "识别当前屏幕")

    def set_dialog_scale(self, percent: int):
        """Scale the dialog and its readable controls around the current top-left."""
        percent = max(50, min(200, int(percent)))
        if percent == self._scale_percent:
            return
        ratio = percent / self._scale_percent
        self._scale_percent = percent
        self.resize(max(460, round(self.width() * ratio)), max(240, round(self.height() * ratio)))
        for widget in (self._name_label, self._text_display, self._input,
                       self._voice_btn, self._screen_btn, self._send_btn):
            font = QFont(widget.font())
            size = font.pointSizeF()
            if size > 0:
                font.setPointSizeF(max(7.0, size * ratio))
                widget.setFont(font)
        control_height = max(32, round(32 * percent / 100))
        self._send_btn.setFixedHeight(control_height)
        self._input.setFixedHeight(control_height)
        self._voice_btn.setFixedHeight(control_height)
        self._screen_btn.setFixedHeight(control_height)

    # ─── 拖拽 ────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() & Qt.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_pos = QPoint()
