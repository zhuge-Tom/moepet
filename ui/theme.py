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
        font-size: 16px;
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
        font-size: 18px;
        line-height: 1.45;
        padding: 10px 12px;
        selection-background-color: #e94560;
    }}
    QLineEdit#input_field {{
        background: {DIALOG_INPUT_BG};
        color: {DIALOG_TEXT};
        border: 1px solid {DIALOG_INPUT_BORDER};
        border-radius: 8px;
        font-size: 16px;
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
        font-size: 14px;
        font-weight: bold;
        padding: 6px 12px;
    }}
    QPushButton#send_btn:hover {{
        background: #ff6b6b;
    }}
    QPushButton#send_btn:pressed {{
        background: #c0392b;
    }}
    QPushButton#voice_btn, QPushButton#screen_btn {{
        background: #24375e;
        color: #dbeafe;
        border: 1px solid #365486;
        border-radius: 8px;
        font-size: 14px;
        padding: 6px 10px;
    }}
    QPushButton#voice_btn:hover, QPushButton#screen_btn:hover {{
        background: #304a7d;
        border-color: #e94560;
        color: white;
    }}
    QPushButton#voice_btn[recording="true"] {{
        background: #e94560;
        color: white;
        border-color: #ff8fa3;
    }}
    QPushButton#voice_btn:disabled, QPushButton#screen_btn:disabled {{
        color: #64748b;
        background: #1e293b;
        border-color: #334155;
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

STAR_CANVAS = "#0b1026"
STAR_SURFACE = "#151d42"
STAR_SURFACE_ELEVATED = "#202b5c"
STAR_INPUT = "#111a3c"
STAR_BORDER = "#485b94"
STAR_BORDER_SOFT = "#31406f"
STAR_TEXT = "#f4f5ff"
STAR_TEXT_MUTED = "#cbd4f4"
STAR_TEXT_SUBTLE = "#9eabd3"
STAR_ACCENT = "#f05c91"
STAR_ACCENT_HOVER = "#ff79aa"
STAR_FOCUS = "#b78cff"
STAR_SUCCESS = "#71d6bb"
STAR_WARNING = "#f5c66b"


SETTINGS_QSS = f"""
    QDialog {{
        background: {STAR_CANVAS};
        color: {STAR_TEXT};
    }}
    QWidget {{ color: {STAR_TEXT}; font-size: 13px; }}
    QLabel {{ background: transparent; }}
    QLineEdit, QTextEdit, QComboBox, QSpinBox {{
        background: {STAR_INPUT}; color: {STAR_TEXT};
        border: 1px solid {STAR_BORDER}; border-radius: 7px;
        padding: 5px 10px; selection-background-color: {STAR_ACCENT};
    }}
    QLineEdit:hover, QTextEdit:hover, QComboBox:hover, QSpinBox:hover {{ border-color: {STAR_FOCUS}; }}
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 2px solid {STAR_FOCUS}; padding: 4px 9px; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox QAbstractItemView {{
        background: {STAR_SURFACE_ELEVATED}; color: {STAR_TEXT}; border: 1px solid {STAR_BORDER};
        selection-background-color: {STAR_ACCENT}; selection-color: #ffffff; outline: none;
    }}
    QComboBox QAbstractItemView::item {{ min-height: 28px; padding: 4px 8px; }}
    QComboBox QAbstractItemView::item:hover {{ background: #293765; }}
    QCheckBox {{ color: {STAR_TEXT}; spacing: 8px; font-size: 13px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border: 2px solid {STAR_BORDER}; border-radius: 5px; background: {STAR_INPUT}; }}
    QCheckBox::indicator:checked {{ background: {STAR_ACCENT}; border-color: {STAR_ACCENT_HOVER}; }}
    QSlider::groove:horizontal {{ height: 5px; background: {STAR_BORDER_SOFT}; border-radius: 3px; }}
    QSlider::sub-page:horizontal {{ background: {STAR_ACCENT}; border-radius: 3px; }}
    QSlider::handle:horizontal {{ width: 15px; height: 15px; margin: -5px 0; background: {STAR_TEXT}; border: 3px solid {STAR_ACCENT}; border-radius: 8px; }}
    QSlider::handle:horizontal:hover {{ border-color: {STAR_FOCUS}; }}
    QPushButton {{
        background: {STAR_SURFACE_ELEVATED}; color: {STAR_TEXT}; border: 1px solid {STAR_BORDER};
        border-radius: 7px; padding: 6px 14px; font-weight: 600;
    }}
    QPushButton:hover {{ background: #293765; border-color: {STAR_FOCUS}; }}
    QPushButton:focus {{ border: 2px solid {STAR_FOCUS}; }}
    QPushButton#settings_primary_button {{ background: {STAR_ACCENT}; border-color: {STAR_ACCENT}; color: #fff; }}
    QPushButton#settings_primary_button:hover {{ background: {STAR_ACCENT_HOVER}; border-color: {STAR_ACCENT_HOVER}; }}
    QPushButton#settings_confirm_button {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #ff76aa, stop:0.48 {STAR_ACCENT}, stop:1 #9c6cff);
        color: #ffffff; border: 1px solid #ff9dca; border-radius: 7px;
        padding: 6px 14px; font-weight: 700;
    }}
    QPushButton#settings_confirm_button:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #ff9dca, stop:0.48 #ff699f, stop:1 #bc8dff);
        border-color: #ffd1e4;
    }}
    QPushButton#settings_confirm_button:pressed {{ background: #d94e83; }}
    QPushButton#settings_secondary_button {{ background: #1b2450; color: {STAR_TEXT_MUTED}; }}
    QPushButton#settings_secondary_button:hover {{ color: {STAR_TEXT}; }}
    QTabWidget::pane {{
        border: 1px solid {STAR_BORDER}; border-radius: 10px;
        background: rgba(20, 28, 64, 210); top: -1px;
    }}
    QTabBar::tab {{
        background: transparent; color: {STAR_TEXT_MUTED}; border: none;
        padding: 9px 16px; margin-right: 3px; font-weight: 600;
    }}
    QTabBar::tab:hover {{ color: #ffffff; background: #293765; border-radius: 7px 7px 0 0; }}
    QTabBar::tab:selected {{
        color: #ffffff; background: {STAR_SURFACE_ELEVATED};
        border-bottom: 3px solid {STAR_ACCENT};
    }}
    QTableWidget {{
        background: #111936; alternate-background-color: #172148;
        color: {STAR_TEXT}; border: 1px solid {STAR_BORDER}; border-radius: 8px;
        gridline-color: {STAR_BORDER_SOFT}; selection-background-color: #34477f;
        selection-color: #ffffff;
    }}
    QHeaderView::section {{
        background: #202b5c; color: #f7f8ff; border: none;
        border-right: 1px solid {STAR_BORDER_SOFT}; border-bottom: 1px solid {STAR_BORDER};
        padding: 8px 10px; font-weight: 700;
    }}
    QTableCornerButton::section {{ background: #202b5c; border: none; }}
    QToolTip {{ background: #293765; color: #ffffff; border: 1px solid {STAR_FOCUS}; padding: 5px; }}
    QScrollBar:vertical {{ width: 7px; background: transparent; margin: 4px 0; }}
    QScrollBar::handle:vertical {{ background: {STAR_BORDER}; border-radius: 3px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {STAR_FOCUS}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""

# Legacy selectors retained for small, older settings widgets that still use
# these object names. New settings surfaces use the star tokens above.
LEGACY_SETTINGS_QSS = """
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
