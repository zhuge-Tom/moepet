"""立绘动画系统

支持淡入淡出切换、弹跳、摇晃、缩放、颤抖等演出效果。
从 ZcChat 的 tachie.cpp 借鉴动画分层思路。
"""

from PySide6.QtCore import (
    QPropertyAnimation, QSequentialAnimationGroup,
    QParallelAnimationGroup, QEasingCurve, QPoint, QSize,
    QObject,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget


class SpriteAnimator(QObject):
    """管理立绘切换动画和演出动画"""

    FADE_DURATION = 250
    ANIM_DURATION = 300

    def __init__(self, parent: QWidget, label: QWidget, label_overlay: QWidget = None):
        super().__init__(parent)
        self._label = label
        self._overlay = label_overlay
        self._active_anims: list[QPropertyAnimation] = []

    def fade_transition(self, new_pixmap):
        """淡入淡出切换立绘"""
        if self._overlay is None:
            self._label.setPixmap(new_pixmap)
            return

        # 把旧图放到 overlay 层做淡出
        self._overlay.setPixmap(self._label.pixmap())
        self._overlay.show()
        self._overlay.setGeometry(self._label.geometry())

        # 新图淡入
        self._label.setPixmap(new_pixmap)
        fade_in = self._opacity_anim(self._label, 0.0, 1.0, self.FADE_DURATION)
        # 旧图淡出
        fade_out = self._opacity_anim(self._overlay, 1.0, 0.0, self.FADE_DURATION + 200)

        fade_in.start()
        fade_out.start()

        self._active_anims = [fade_in, fade_out]

    def play(self, anim_type: str, base_pos: QPoint = None, base_size: QSize = None):
        """播放演出动画"""
        if not base_pos:
            base_pos = self._label.pos()
        if not base_size:
            base_size = self._label.size()

        dispatch = {
            "bounce": self._anim_bounce,
            "shake": self._anim_shake,
            "enlarge": self._anim_enlarge,
            "shrink": self._anim_shrink,
            "tremble": self._anim_tremble,
            "swing": self._anim_swing,
        }
        fn = dispatch.get(anim_type)
        if fn:
            fn(base_pos, base_size)

    # --- 各类动画实现 ---

    def _anim_bounce(self, base_pos: QPoint, _size: QSize):
        """上下弹跳"""
        group = QSequentialAnimationGroup(self._label)
        up = QPropertyAnimation(self._label, b"pos")
        up.setDuration(150)
        up.setStartValue(base_pos)
        up.setEndValue(base_pos + QPoint(0, -20))
        up.setEasingCurve(QEasingCurve.OutQuad)

        down = QPropertyAnimation(self._label, b"pos")
        down.setDuration(200)
        down.setStartValue(base_pos + QPoint(0, -20))
        down.setEndValue(base_pos)
        down.setEasingCurve(QEasingCurve.InBounce)

        group.addAnimation(up)
        group.addAnimation(down)
        group.start()
        self._active_anims = [group]

    def _anim_swing(self, base_pos: QPoint, _size: QSize):
        """左右摇摆"""
        group = QSequentialAnimationGroup(self._label)
        offsets = [(-18, 0), (18, 0), (-10, 0), (10, 0), (0, 0)]
        prev = base_pos
        for dx, dy in offsets:
            target = base_pos + QPoint(dx, dy)
            a = QPropertyAnimation(self._label, b"pos")
            a.setDuration(100)
            a.setStartValue(prev)
            a.setEndValue(target)
            a.setEasingCurve(QEasingCurve.InOutSine)
            group.addAnimation(a)
            prev = target
        group.start()
        self._active_anims = [group]

    def _anim_shake(self, base_pos: QPoint, _size: QSize):
        """快速抖动"""
        group = QSequentialAnimationGroup(self._label)
        for _ in range(6):
            for dx, dy in [(0, -5), (0, 5), (-5, 0), (5, 0)]:
                a = QPropertyAnimation(self._label, b"pos")
                a.setDuration(30)
                a.setStartValue(base_pos + QPoint(-dx, -dy))
                a.setEndValue(base_pos + QPoint(dx, dy))
                group.addAnimation(a)
        # 回到原位
        final = QPropertyAnimation(self._label, b"pos")
        final.setDuration(30)
        final.setStartValue(base_pos + QPoint(5, 0))
        final.setEndValue(base_pos)
        group.addAnimation(final)
        group.start()
        self._active_anims = [group]

    def _anim_enlarge(self, _pos: QPoint, base_size: QSize):
        """放大演出"""
        target = QSize(int(base_size.width() * 1.2), int(base_size.height() * 1.2))
        a = QPropertyAnimation(self._label, b"size")
        a.setDuration(self.ANIM_DURATION)
        a.setStartValue(base_size)
        a.setEndValue(target)
        a.setEasingCurve(QEasingCurve.OutBack)
        a.finished.connect(lambda: self._restore_size(base_size))
        a.start()
        self._active_anims = [a]

    def _anim_shrink(self, _pos: QPoint, base_size: QSize):
        """缩小演出"""
        target = QSize(int(base_size.width() * 0.85), int(base_size.height() * 0.85))
        a = QPropertyAnimation(self._label, b"size")
        a.setDuration(self.ANIM_DURATION)
        a.setStartValue(base_size)
        a.setEndValue(target)
        a.setEasingCurve(QEasingCurve.InOutQuad)
        a.finished.connect(lambda: self._restore_size(base_size))
        a.start()
        self._active_anims = [a]

    def _anim_tremble(self, base_pos: QPoint, _size: QSize):
        """持续颤抖"""
        group = QSequentialAnimationGroup(self._label)
        for _ in range(12):
            for dx, dy in [(0, -3), (3, 0), (0, 3), (-3, 0)]:
                a = QPropertyAnimation(self._label, b"pos")
                a.setDuration(25)
                a.setStartValue(base_pos)
                a.setEndValue(base_pos + QPoint(dx, dy))
                group.addAnimation(a)
        final = QPropertyAnimation(self._label, b"pos")
        final.setDuration(25)
        final.setStartValue(base_pos + QPoint(-3, 0))
        final.setEndValue(base_pos)
        group.addAnimation(final)
        group.start()
        self._active_anims = [group]

    def _restore_size(self, size: QSize):
        """动画结束后恢复原始尺寸"""
        a = QPropertyAnimation(self._label, b"size")
        a.setDuration(200)
        a.setStartValue(self._label.size())
        a.setEndValue(size)
        a.setEasingCurve(QEasingCurve.InOutQuad)
        a.start()
        self._active_anims.append(a)

    @staticmethod
    def _opacity_anim(widget: QWidget, start: float, end: float, duration: int) -> QPropertyAnimation:
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        a = QPropertyAnimation(effect, b"opacity")
        a.setDuration(duration)
        a.setStartValue(start)
        a.setEndValue(end)
        a.setEasingCurve(QEasingCurve.InOutCubic)
        return a
