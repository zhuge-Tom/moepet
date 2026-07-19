"""Normalize transparent portraits to a shared character scale and anchor."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QPainter, QPixmap, QRegion


@dataclass(frozen=True)
class PortraitLayout:
    canvas_width: int
    canvas_height: int
    character_width: int
    character_height: int
    bottom_margin: int


def opaque_bounds(pixmap: QPixmap) -> QRect:
    """Return the non-transparent bounds used to align a portrait."""
    return QRegion(pixmap.mask()).boundingRect()


def common_layout(pixmaps: list[QPixmap]) -> PortraitLayout | None:
    """Use medians so one unusually exported portrait cannot set the scale."""
    samples = [(pm, opaque_bounds(pm)) for pm in pixmaps if not pm.isNull()]
    samples = [(pm, rect) for pm, rect in samples if not rect.isEmpty()]
    if not samples:
        return None
    return PortraitLayout(
        canvas_width=round(median(pm.width() for pm, _ in samples)),
        canvas_height=round(median(pm.height() for pm, _ in samples)),
        character_width=round(median(rect.width() for _, rect in samples)),
        character_height=round(median(rect.height() for _, rect in samples)),
        bottom_margin=round(median(pm.height() - rect.bottom() - 1 for pm, rect in samples)),
    )


def normalize_portrait(pixmap: QPixmap, layout: PortraitLayout) -> QPixmap:
    """Scale the visible character and place it on a stable bottom-center anchor."""
    bounds = opaque_bounds(pixmap)
    if pixmap.isNull() or bounds.isEmpty():
        return pixmap
    character = pixmap.copy(bounds).scaledToHeight(
        layout.character_height,
        Qt.SmoothTransformation,
    )
    result = QPixmap(layout.canvas_width, layout.canvas_height)
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.drawPixmap(
        (layout.canvas_width - character.width()) // 2,
        layout.canvas_height - layout.bottom_margin - character.height(),
        character,
    )
    painter.end()
    return result
