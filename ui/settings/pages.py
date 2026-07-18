"""Small independent settings pages.

Pages are intentionally pure widgets.  The settings window owns navigation and
form persistence while individual pages own their own presentation tree.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


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
