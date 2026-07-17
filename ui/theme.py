"""QSS 主题常量

集中管理样式表，方便统一调整。
"""

DIALOG_BG = "#1a1a2e"
DIALOG_BORDER = "#e94560"
DIALOG_TEXT = "#eee"
DIALOG_NAME_BG = "#e94560"
DIALOG_NAME_TEXT = "#fff"
DIALOG_INPUT_BG = "#16213e"
DIALOG_INPUT_BORDER = "#0f3460"
DIALOG_BTN_HOVER = "#e94560"

DIALOG_QSS = f"""
    QDialog {{
        background: {DIALOG_BG};
        border: 2px solid {DIALOG_BORDER};
        border-radius: 12px;
    }}
    QLabel#name_label {{
        background: {DIALOG_NAME_BG};
        color: {DIALOG_NAME_TEXT};
        font-size: 14px;
        font-weight: bold;
        padding: 4px 16px;
        border-radius: 0 0 10px 0;
    }}
    QLabel#text_label {{
        color: {DIALOG_TEXT};
        font-size: 14px;
        padding: 8px 16px;
        background: transparent;
    }}
    QTextEdit#chat_display {{
        background: {DIALOG_INPUT_BG};
        color: {DIALOG_TEXT};
        border: 1px solid {DIALOG_INPUT_BORDER};
        border-radius: 8px;
        font-size: 13px;
        padding: 8px;
        selection-background-color: #e94560;
    }}
    QLineEdit#input_field {{
        background: {DIALOG_INPUT_BG};
        color: {DIALOG_TEXT};
        border: 1px solid {DIALOG_INPUT_BORDER};
        border-radius: 8px;
        font-size: 13px;
        padding: 8px 12px;
    }}
    QLineEdit#input_field:focus {{
        border-color: {DIALOG_BORDER};
    }}
    QPushButton#send_btn {{
        background: {DIALOG_BORDER};
        color: white;
        border: none;
        border-radius: 8px;
        font-size: 13px;
        font-weight: bold;
        padding: 6px 12px;
    }}
    QPushButton#send_btn:hover {{
        background: #ff6b6b;
    }}
    QPushButton#send_btn:pressed {{
        background: #c0392b;
    }}
    QPushButton#history_btn {{
        background: transparent;
        color: #888;
        border: 1px solid #333;
        border-radius: 6px;
        font-size: 11px;
        padding: 4px 10px;
    }}
    QPushButton#history_btn:hover {{
        border-color: {DIALOG_BORDER};
        color: {DIALOG_BORDER};
    }}
"""

SETTINGS_QSS = """
    QDialog {
        background: #f5f7fa;
    }
    QFrame#nav_panel {
        background: #2c3e50;
        border: none;
    }
    QFrame#nav_panel QPushButton {
        background: transparent;
        color: #ecf0f1;
        border: none;
        text-align: left;
        padding: 10px 16px;
        font-size: 13px;
        border-radius: 6px;
    }
    QFrame#nav_panel QPushButton:hover {
        background: rgba(255,255,255,0.1);
    }
    QFrame#nav_panel QPushButton[active="true"] {
        background: #e94560;
        color: white;
        font-weight: bold;
    }
    QLabel#page_title {
        font-size: 20px;
        font-weight: bold;
        color: #2c3e50;
        padding: 4px 0;
    }
    QFrame#card {
        background: white;
        border-radius: 12px;
        border: 1px solid #e8ecf1;
    }
    QLabel#section_title {
        font-size: 13px;
        font-weight: bold;
        color: #7f8c8d;
        padding-top: 6px;
    }
    QCheckBox {
        font-size: 13px;
        color: #2c3e50;
        spacing: 8px;
    }
    QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 2px solid #bdc3c7;
    }
    QCheckBox::indicator:checked {
        background: #e94560;
        border-color: #e94560;
    }
    QSlider::groove:horizontal {
        height: 4px;
        background: #e8ecf1;
        border-radius: 2px;
    }
    QSlider::handle:horizontal {
        width: 16px;
        height: 16px;
        margin: -6px 0;
        background: #e94560;
        border-radius: 8px;
    }
    QSlider::handle:horizontal:hover {
        background: #ff6b6b;
    }
    QComboBox {
        border: 1px solid #e8ecf1;
        border-radius: 6px;
        padding: 6px 12px;
        font-size: 13px;
        background: white;
    }
    QComboBox:hover {
        border-color: #e94560;
    }
    QComboBox::drop-down {
        border: none;
        width: 24px;
    }
    QPushButton#primary_btn {
        background: #e94560;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 8px 24px;
        font-size: 13px;
        font-weight: bold;
    }
    QPushButton#primary_btn:hover {
        background: #ff6b6b;
    }
    QPushButton#secondary_btn {
        background: white;
        color: #2c3e50;
        border: 1px solid #e8ecf1;
        border-radius: 8px;
        padding: 8px 24px;
        font-size: 13px;
    }
    QPushButton#secondary_btn:hover {
        background: #f5f7fa;
    }
"""
