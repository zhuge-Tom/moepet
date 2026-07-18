"""Reusable visual building blocks for Moepet's settings experience.

These components deliberately contain presentation only. Pages own their
configuration values and actions, mirroring the separation used by Sakura.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class SettingsSection(QFrame):
    """A softly separated group of related settings controls."""

    def __init__(self, title: str, description: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("settings_section")
        self.setStyleSheet("""
            QFrame#settings_section {
                background: #ffffff;
                border: 1px solid #e7ebf3;
                border-radius: 10px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 14px; font-weight: 700; color: #1e293b;")
        layout.addWidget(heading)
        if description:
            hint = QLabel(description)
            hint.setWordWrap(True)
            hint.setStyleSheet("font-size: 12px; color: #64748b;")
            layout.addWidget(hint)
        self.content = layout


class ServiceStatusCard(QFrame):
    """Compact provider summary that keeps setup state visible at a glance."""

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.setObjectName("service_status_card")
        self.setStyleSheet("""
            QFrame#service_status_card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        text = QVBoxLayout()
        name = QLabel(title)
        name.setStyleSheet("font-weight: 700; color: #334155;")
        text.addWidget(name)
        detail = QLabel(subtitle)
        detail.setWordWrap(True)
        detail.setStyleSheet("font-size: 12px; color: #64748b;")
        text.addWidget(detail)
        layout.addLayout(text, 1)
        self.badge = QLabel("未配置")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setMinimumWidth(58)
        self.set_state(False)
        layout.addWidget(self.badge)

    def set_state(self, ready: bool) -> None:
        self.badge.setText("已就绪" if ready else "需配置")
        color = "#15803d" if ready else "#a16207"
        background = "#dcfce7" if ready else "#fef3c7"
        self.badge.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {color}; background: {background};"
            "border-radius: 9px; padding: 4px 8px;"
        )


class IntegrationOverview(QFrame):
    """Clickable setup summary used as the first-stop settings dashboard."""

    def __init__(self, title: str, items: list[tuple[str, str, bool, str]], on_open, parent=None):
        super().__init__(parent)
        self.setObjectName("integration_overview")
        self.setStyleSheet("""
            QFrame#integration_overview { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; }
            QPushButton { text-align: left; background: #f8fafc; color: #334155; border: 1px solid #e8edf4;
                          border-radius: 8px; padding: 10px 12px; font-size: 12px; }
            QPushButton:hover { background: #fff1f3; border-color: #f3a7b4; color: #9f1239; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 15px; font-weight: 700; color: #1e293b;")
        layout.addWidget(heading)
        subtitle = QLabel("按顺序完成连接，角色就可以聊天、听你说话、朗读回复并理解屏幕。")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size: 12px; color: #64748b;")
        layout.addWidget(subtitle)
        for name, detail, ready, page_key in items:
            state = "已就绪" if ready else "待配置"
            button = QPushButton(f"{name}  ·  {state}\n{detail}")
            button.clicked.connect(lambda _checked=False, key=page_key: on_open(key))
            layout.addWidget(button)
