"""Reusable visual building blocks for Moepet's starry settings experience."""

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.theme import (
    STAR_ACCENT, STAR_BORDER, STAR_FOCUS, STAR_SUCCESS, STAR_SURFACE,
    STAR_SURFACE_ELEVATED, STAR_TEXT, STAR_TEXT_MUTED, STAR_WARNING,
)


class StarfieldBackground(QWidget):
    """A dense deterministic star field with brief, low-cost meteor showers."""

    _stars = (
        (0.05, 0.11, 1.2), (0.12, 0.37, 0.8), (0.19, 0.16, 1.6),
        (0.25, 0.71, 1.1), (0.32, 0.28, 0.9), (0.39, 0.07, 1.4),
        (0.47, 0.53, 1.1), (0.54, 0.20, 0.8), (0.61, 0.78, 1.3),
        (0.68, 0.12, 1.7), (0.73, 0.43, 0.9), (0.81, 0.27, 1.1),
        (0.89, 0.66, 1.5), (0.94, 0.18, 0.9), (0.97, 0.48, 1.2),
        (0.03, 0.58, 0.8), (0.08, 0.82, 1.3), (0.15, 0.24, 1.0),
        (0.22, 0.49, 1.7), (0.28, 0.90, 0.7), (0.35, 0.40, 1.1),
        (0.42, 0.84, 1.5), (0.50, 0.32, 1.0), (0.57, 0.63, 1.6),
        (0.64, 0.04, 0.9), (0.70, 0.56, 1.2), (0.76, 0.88, 0.8),
        (0.84, 0.35, 1.4), (0.91, 0.78, 1.0), (0.99, 0.09, 1.5),
        (0.02, 0.18, 0.7), (0.04, 0.73, 1.1), (0.07, 0.44, 0.8),
        (0.10, 0.66, 1.5), (0.13, 0.94, 0.9), (0.17, 0.52, 1.2),
        (0.20, 0.06, 0.8), (0.24, 0.36, 1.1), (0.27, 0.64, 0.9),
        (0.30, 0.13, 1.3), (0.33, 0.56, 0.8), (0.37, 0.95, 1.4),
        (0.40, 0.17, 0.7), (0.44, 0.67, 1.2), (0.48, 0.92, 0.9),
        (0.52, 0.10, 1.4), (0.55, 0.43, 0.8), (0.59, 0.90, 1.1),
        (0.62, 0.34, 0.7), (0.66, 0.68, 1.3), (0.69, 0.22, 0.9),
        (0.72, 0.74, 1.4), (0.75, 0.47, 0.8), (0.79, 0.96, 1.2),
        (0.82, 0.15, 0.9), (0.86, 0.53, 1.3), (0.90, 0.30, 0.8),
        (0.93, 0.91, 1.2), (0.96, 0.60, 0.9), (0.98, 0.82, 1.4),
    )
    _constellations = (
        ((0.70, 0.15), (0.75, 0.22), (0.79, 0.18), (0.83, 0.28), (0.78, 0.34)),
        ((0.08, 0.69), (0.13, 0.62), (0.19, 0.68), (0.17, 0.78), (0.10, 0.82)),
        ((0.52, 0.78), (0.57, 0.71), (0.63, 0.76), (0.60, 0.87)),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._meteor_progress = -1.0
        self._meteor_origins = ()
        self._meteor_timer = QTimer(self)
        self._meteor_timer.setInterval(50)
        self._meteor_timer.timeout.connect(self._advance_meteor)
        self._meteor_cycle = QTimer(self)
        self._meteor_cycle.setInterval(9000)
        self._meteor_cycle.timeout.connect(self._start_meteor)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._meteor_cycle.start()

    def hideEvent(self, event) -> None:
        self._meteor_cycle.stop()
        self._meteor_timer.stop()
        self._meteor_progress = -1.0
        super().hideEvent(event)

    def _start_meteor(self) -> None:
        if self._meteor_timer.isActive() or not self.isVisible():
            return
        # Three fixed lanes create a shower without random work or persistent animation.
        self._meteor_origins = (
            ((0.12, 0.08), 0.00),
            ((0.42, 0.04), 0.16),
            ((0.68, 0.10), 0.31),
        )
        self._meteor_progress = 0.0
        self._meteor_timer.start()
        self.update()

    def _advance_meteor(self) -> None:
        self._meteor_progress += 0.09
        if self._meteor_progress > 1.0:
            self._meteor_progress = -1.0
            self._meteor_timer.stop()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, QColor("#090d20"))
        gradient.setColorAt(0.52, QColor("#13183b"))
        gradient.setColorAt(1.0, QColor("#21163f"))
        painter.fillRect(rect, gradient)

        # Two fixed glows supply depth without animation or image assets.
        for x, y, radius, color in (
            (rect.width() * 0.82, rect.height() * 0.10, rect.width() * 0.36, "#633b9a"),
            (rect.width() * 0.16, rect.height() * 0.84, rect.width() * 0.30, "#1d4a8a"),
        ):
            glow = QRadialGradient(x, y, radius)
            glow_color = QColor(color)
            glow_color.setAlpha(72)
            clear = QColor(color)
            clear.setAlpha(0)
            glow.setColorAt(0.0, glow_color)
            glow.setColorAt(1.0, clear)
            painter.fillRect(rect, glow)

        painter.setPen(Qt.NoPen)
        for x, y, size in self._stars:
            painter.setBrush(QColor("#f5efff"))
            painter.drawEllipse(int(rect.width() * x), int(rect.height() * y), int(size), int(size))

        self._paint_constellations(painter, rect)

        if self._meteor_progress >= 0:
            for origin, delay in self._meteor_origins:
                progress = (self._meteor_progress - delay) / 0.69
                if 0 <= progress <= 1:
                    self._paint_meteor(painter, rect, origin, progress)

    def _paint_constellations(self, painter: QPainter, rect) -> None:
        line = QColor("#9ea7e8")
        line.setAlpha(68)
        painter.setPen(QPen(line, 0.8))
        for constellation in self._constellations:
            points = [(rect.width() * x, rect.height() * y) for x, y in constellation]
            for start, end in zip(points, points[1:]):
                painter.drawLine(int(start[0]), int(start[1]), int(end[0]), int(end[1]))
            painter.setBrush(QColor("#dfe5ff"))
            for x, y in points:
                painter.drawEllipse(int(x - 1), int(y - 1), 3, 3)

    def _paint_meteor(self, painter: QPainter, rect, origin, progress: float) -> None:
        start_x = rect.width() * origin[0]
        start_y = rect.height() * origin[1]
        head_x = start_x + rect.width() * 0.42 * progress
        head_y = start_y + rect.height() * 0.25 * progress
        tail_x = head_x - rect.width() * 0.10
        tail_y = head_y - rect.height() * 0.06
        tail = QLinearGradient(tail_x, tail_y, head_x, head_y)
        clear = QColor("#f7dcff")
        clear.setAlpha(0)
        glow = QColor("#d6bdff")
        glow.setAlpha(125)
        tail.setColorAt(0.0, clear)
        tail.setColorAt(0.78, glow)
        tail.setColorAt(1.0, QColor("#ffffff"))
        painter.setPen(QPen(tail, 2.4, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(int(tail_x), int(tail_y), int(head_x), int(head_y))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(int(head_x - 2), int(head_y - 2), 4, 4)


class SettingsSection(QFrame):
    """A softly separated group of related settings controls."""

    def __init__(self, title: str, description: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("settings_section")
        self.setStyleSheet(
            f"QFrame#settings_section {{ background: {STAR_SURFACE}; border: 1px solid {STAR_BORDER}; border-radius: 10px; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {STAR_TEXT};")
        layout.addWidget(heading)
        if description:
            hint = QLabel(description)
            hint.setWordWrap(True)
            hint.setStyleSheet(f"font-size: 12px; color: {STAR_TEXT_MUTED};")
            layout.addWidget(hint)
        self.content = layout


class ServiceStatusCard(QFrame):
    """Compact provider summary that keeps setup state visible at a glance."""

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.setObjectName("service_status_card")
        self.setStyleSheet(
            f"QFrame#service_status_card {{ background: {STAR_SURFACE_ELEVATED}; border: 1px solid {STAR_BORDER}; border-radius: 10px; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        text = QVBoxLayout()
        name = QLabel(title)
        name.setStyleSheet(f"font-weight: 700; color: {STAR_TEXT};")
        text.addWidget(name)
        detail = QLabel(subtitle)
        detail.setWordWrap(True)
        detail.setStyleSheet(f"font-size: 12px; color: {STAR_TEXT_MUTED};")
        text.addWidget(detail)
        layout.addLayout(text, 1)
        self.badge = QLabel("未配置")
        self.badge.setObjectName("service_status_badge")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setMinimumWidth(58)
        self.set_state(False)
        layout.addWidget(self.badge)

    def set_state(self, ready: bool) -> None:
        self.badge.setText("已就绪" if ready else "需配置")
        color = STAR_SUCCESS if ready else STAR_WARNING
        background = "#173c43" if ready else "#4a3820"
        self.badge.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {color}; background: {background};"
            "border-radius: 9px; padding: 4px 8px;"
        )


class IntegrationOverview(QFrame):
    """Clickable setup summary used as the first-stop settings dashboard."""

    def __init__(self, title: str, items: list[tuple[str, str, bool, str]], on_open, parent=None):
        super().__init__(parent)
        self.setObjectName("integration_overview")
        self.setStyleSheet(f"""
            QFrame#integration_overview {{ background: {STAR_SURFACE}; border: 1px solid {STAR_BORDER}; border-radius: 12px; }}
            QPushButton {{ text-align: left; background: {STAR_SURFACE_ELEVATED}; color: {STAR_TEXT}; border: 1px solid {STAR_BORDER};
                            border-radius: 8px; padding: 10px 12px; font-size: 12px; }}
            QPushButton:hover {{ background: #293765; border-color: {STAR_FOCUS}; color: #ffffff; }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        heading = QLabel(title)
        heading.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {STAR_TEXT};")
        layout.addWidget(heading)
        subtitle = QLabel("按顺序完成连接，角色就可以聊天、听你说话、朗读回复并理解屏幕。")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"font-size: 12px; color: {STAR_TEXT_MUTED};")
        layout.addWidget(subtitle)
        for name, detail, ready, page_key in items:
            state = "已就绪" if ready else "待配置"
            button = QPushButton(f"{name} · {state}\n{detail}")
            button.clicked.connect(lambda _checked=False, key=page_key: on_open(key))
            layout.addWidget(button)
