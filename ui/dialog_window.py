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

from ui.theme import DIALOG_QSS


class DialogWindow(QDialog):
    """Galgame 风格对话框"""

    text_submitted = Signal(str)

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

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(DIALOG_QSS)
        self.setMinimumSize(400, 160)
        self.resize(480, 200)

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
        self._text_display.setMinimumHeight(80)
        self._text_display.setMaximumHeight(200)
        frame_layout.addWidget(self._text_display, 1)

        # 底部操作栏
        bottom = QHBoxLayout()
        bottom.setContentsMargins(12, 6, 12, 0)
        bottom.setSpacing(8)

        self._history_btn = QPushButton("📜 历史")
        self._history_btn.setObjectName("history_btn")
        self._history_btn.setFixedHeight(28)
        self._history_btn.clicked.connect(self._toggle_history)
        bottom.addWidget(self._history_btn)

        bottom.addStretch()

        self._input = QLineEdit()
        self._input.setObjectName("input_field")
        self._input.setPlaceholderText("说点什么...")
        self._input.setFixedHeight(32)
        self._input.returnPressed.connect(self._on_submit)
        bottom.addWidget(self._input, 1)

        self._send_btn = QPushButton("发送")
        self._send_btn.setObjectName("send_btn")
        self._send_btn.setFixedSize(56, 32)
        self._send_btn.clicked.connect(self._on_submit)
        bottom.addWidget(self._send_btn)

        frame_layout.addLayout(bottom)
        root.addWidget(frame)

        # 历史面板（默认隐藏）
        self._history_panel = QScrollArea()
        self._history_panel.setWidgetResizable(True)
        self._history_panel.setFrameShape(QFrame.NoFrame)
        self._history_panel.setMaximumHeight(0)
        self._history_panel.setStyleSheet("""
            QScrollArea { background: #0f0f23; border-radius: 0 0 12px 12px; }
            QScrollBar:vertical { width: 4px; background: transparent; }
            QScrollBar::handle:vertical { background: #e94560; border-radius: 2px; }
        """)
        self._history_container = QWidget()
        self._history_layout = QVBoxLayout(self._history_container)
        self._history_layout.setContentsMargins(12, 8, 12, 8)
        self._history_layout.setSpacing(6)
        self._history_layout.addStretch()
        self._history_panel.setWidget(self._history_container)
        root.addWidget(self._history_panel)

    # ─── 文本显示 ─────────────────────────────

    def display_text(self, text: str, role: str = "assistant"):
        """逐字显示文本"""
        if self._typing:
            self._typing_timer.stop()

        # 存入历史
        self._history.append({"role": role, "text": text})
        self._add_history_bubble(role, text)

        # 开始逐字显示
        self._full_text = text
        self._typed_index = 0
        self._typing = True
        self._text_display.clear()
        self._typing_timer.start()

    def display_instant(self, text: str, role: str = "user"):
        """立即显示文本（用户消息用）"""
        self._history.append({"role": role, "text": text})
        self._add_history_bubble(role, text)
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
            self._history.append({"role": "assistant", "text": text})
            self._add_history_bubble("assistant", text)

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

    def _add_history_bubble(self, role: str, text: str):
        """在历史面板添加消息气泡"""
        bubble = QLabel(f"{'你' if role == 'user' else self._char_name}: {text}")
        bubble.setWordWrap(True)
        bubble.setStyleSheet(f"""
            QLabel {{
                background: {'#0f3460' if role == 'user' else '#2d1b3d'};
                color: #eee;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 12px;
            }}
        """)
        # 插入到 stretch 之前
        count = self._history_layout.count()
        self._history_layout.insertWidget(max(0, count - 1), bubble)

    # ─── 输入处理 ─────────────────────────────

    def _on_submit(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self.display_instant(text, "user")
        self.text_submitted.emit(text)

    # ─── 历史面板 ─────────────────────────────

    def _toggle_history(self):
        if self._history_panel.maximumHeight() > 0:
            self._history_panel.setMaximumHeight(0)
        else:
            self._history_panel.setMaximumHeight(200)

    # ─── 外部接口 ─────────────────────────────

    def set_character_name(self, name: str):
        self._char_name = name
        self._name_label.setText(name)

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
