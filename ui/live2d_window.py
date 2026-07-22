"""Cubism 3 desktop-pet window backed by the optional live2d-py runtime."""

from pathlib import Path
import math
import random
import time

from PySide6.QtCore import QRectF, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QCursor, QPainter, QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget

from ui.pet_window import PetWindow

_runtime_initialized = False


class MouthOverlay(QWidget):
    """A reliable mouth layer above the OpenGL model at small pet scales."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._openness = 0.0
        self._drag_target = (0.0, 0.0)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

    def set_pose(self, openness: float, x: float, y: float) -> None:
        self._openness = max(0.0, min(1.0, openness))
        self._drag_target = (x, y)
        self.update()

    def paintEvent(self, event) -> None:
        if self._openness <= 0.01:
            return
        x, y = self._drag_target
        center_x = self.width() * 0.515 + x * self.width() * 0.012
        # Noir's face sits lower than the artboard center at pet scale.
        center_y = self.height() * 0.645 - y * self.height() * 0.008
        mouth_width = max(9.0, self.width() * 0.034)
        mouth_height = 2.2 + self._openness * max(6.5, self.height() * 0.014)
        rect = QRectF(
            center_x - mouth_width / 2, center_y - mouth_height / 2,
            mouth_width, mouth_height,
        )
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(82, 45, 63, 226))
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.end()


class Live2DCanvas(QOpenGLWidget):
    """Transparent OpenGL surface that owns one Cubism 3 model instance."""

    initialization_failed = Signal(str)
    mouth_pose_changed = Signal(float, float, float)

    def __init__(self, model_path: Path, parent=None):
        super().__init__(parent)
        self._model_path = Path(model_path)
        self._model = None
        self._canvas = None
        self._scale = 1.0
        self._drag_target = (0.0, 0.0)
        self._speaking = False
        self._expression = ""
        self._applied_expression = None
        self._speech_started_at = 0.0
        self._lipsync = None
        self._mouth_open = 0.0
        self._line_eye_active = False
        self._last_frame_at = time.monotonic()
        self._render_timer_id = None
        surface = QSurfaceFormat()
        surface.setAlphaBufferSize(8)
        surface.setDepthBufferSize(24)
        self.setFormat(surface)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)

    def initializeGL(self) -> None:
        try:
            import live2d.v3 as live2d
            from live2d.utils.canvas import Canvas

            global _runtime_initialized
            if not _runtime_initialized:
                live2d.init()
                _runtime_initialized = True
            live2d.glInit()
            self._model = live2d.LAppModel()
            self._model.LoadModelJson(str(self._model_path))
            self._model.SetAutoBlinkEnable(True)
            self._model.SetAutoBreathEnable(True)
            self._load_model_expressions()
            self.set_expression(self._expression, force=True)
            self._canvas = Canvas()
            self.set_rendering_enabled(True)
        except Exception as exc:
            self._model = None
            self.initialization_failed.emit(f"Live2D 初始化失败：{exc}")

    def resizeGL(self, width: int, height: int) -> None:
        if self._model is not None:
            self._model.Resize(width, height)
            self._model.SetScale(self._scale)
        if self._canvas is not None:
            self._canvas.SetSize(width, height)

    def paintGL(self) -> None:
        if self._model is None or self._canvas is None:
            return
        import live2d.v3 as live2d

        self._canvas.Draw(lambda: (live2d.clearBuffer(), self._model.Draw()))
        self._paint_speech_mouth()

    def _paint_speech_mouth(self) -> None:
        """Draw the fallback mouth in the OpenGL widget's own paint pass.

        A child QWidget can be composited behind a transparent QOpenGLWidget
        on Windows. Drawing here keeps the visual mouth above the model in
        the same surface as the native ParamMouthOpenY animation.
        """
        if not self._speaking or self._mouth_open <= 0.02:
            return
        x, y = self._drag_target
        center_x = self.width() * (0.515 + x * 0.012)
        center_y = self.height() * (0.645 - y * 0.008)
        mouth_width = max(14.0, self.width() * 0.052)
        mouth_height = 2.8 + self._mouth_open * max(11.0, self.height() * 0.026)
        rect = QRectF(
            center_x - mouth_width / 2, center_y - mouth_height / 2,
            mouth_width, mouth_height,
        )
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor(232, 173, 191, 180))
        painter.setBrush(QColor(78, 31, 47, 238))
        painter.drawRoundedRect(rect, mouth_height / 2, mouth_height / 2)
        painter.end()

    def timerEvent(self, event) -> None:
        if event.timerId() != self._render_timer_id:
            super().timerEvent(event)
            return
        if self._model is not None:
            now = time.monotonic()
            elapsed = min(now - self._last_frame_at, 0.1)
            self._last_frame_at = now
            self._advance_model(elapsed)
        self.update()

    def set_rendering_enabled(self, enabled: bool) -> None:
        """Stop all per-frame work while the transparent pet is hidden."""
        if enabled and self._render_timer_id is None:
            self._last_frame_at = time.monotonic()
            self._render_timer_id = self.startTimer(33)
        elif not enabled and self._render_timer_id is not None:
            self.killTimer(self._render_timer_id)
            self._render_timer_id = None

    def set_model_scale(self, scale: float) -> None:
        self._scale = max(0.1, float(scale))
        if self._model is not None:
            self._model.SetScale(self._scale)
        self.update()

    def set_drag_target(self, x: float, y: float) -> None:
        """Set Cubism's normalized eye/head target in the -1..1 range."""
        self._drag_target = (max(-1.0, min(1.0, x)), max(-1.0, min(1.0, y)))

    def set_speaking(self, speaking: bool) -> None:
        self._speaking = bool(speaking)
        if self._speaking:
            self._speech_started_at = time.monotonic()
        else:
            self._lipsync = None
            self._mouth_open = 0.0
            if self._model is not None:
                self._model._model.SetParameterValueById("ParamMouthOpenY", 0.0)

    def set_visual_mouth_open(self, openness: float) -> None:
        """Refresh the visible mouth even when the native render tick lags."""
        if not self._speaking:
            return
        self._mouth_open = max(0.0, min(1.0, float(openness)))
        self.update()

    def start_lipsync(self, audio_path: str) -> None:
        """Drive the mouth from the generated WAV while Qt plays it."""
        self.set_speaking(True)
        try:
            from live2d.utils.lipsync import WavHandler

            handler = WavHandler()
            handler.Start(audio_path)
            self._lipsync = handler if handler.pcmData is not None else None
        except Exception:
            # Keep the lightweight procedural fallback if the WAV is unreadable.
            self._lipsync = None

    def set_expression(self, expression: str, force: bool = False) -> None:
        expression = expression or ""
        if not force and expression == self._expression:
            return
        self._expression = expression
        if self._model is None:
            return
        if expression:
            self._model.SetExpression(expression)
        else:
            self._model.ResetExpression()
        self._applied_expression = expression

    def set_line_eye_active(self, active: bool) -> None:
        """Keep Noir's Param40 line-eye visible after Cubism auto updates."""
        self._line_eye_active = bool(active)

    def _load_model_expressions(self) -> None:
        for path in sorted(self._model_path.parent.glob("*.exp3.json")):
            expression_id = path.name.removesuffix(".exp3.json")
            self._model.LoadExtraExpression(expression_id, str(path))

    def _advance_model(self, elapsed: float) -> None:
        """Run the Cubism update stages the wrapper leaves opt-in."""
        model = self._model._model
        self._model.Drag(*self._drag_target)
        model.LoadParameters()
        model.UpdateMotion(elapsed)
        model.SaveParameters()
        model.UpdateBlink(elapsed)
        model.UpdateExpression(elapsed)
        model.UpdateDrag(elapsed)
        model.UpdateBreath(elapsed)
        self._update_lipsync()
        model.UpdatePhysics(elapsed)
        model.UpdatePose(elapsed)
        model.Update(elapsed)
        self._apply_visible_parameters()

    def _apply_visible_parameters(self) -> None:
        """Apply interaction inputs after physics so they reach the draw call.

        The bundled wrapper's Drag target is overwritten by its native update
        stages.  Noir exposes standard Cubism head and eye parameters, so
        writing those final values provides stable cursor tracking while the
        model's hair and ears still receive their normal physics update.
        """
        x, y = self._drag_target
        # The model's authored X axis matches desktop left/right.  Use its
        # full range so the turn remains obvious at desktop-pet scale.
        self._model.SetParameterValue("ParamAngleX", x * 30.0)
        self._model.SetParameterValue("ParamAngleY", y * 18.0)
        self._model.SetParameterValue("ParamEyeBallX", -x)
        self._model.SetParameterValue("ParamEyeBallY", y)
        # Noir maps ParamMouthOpenY from 0 (closed) to 2.1 (fully open).
        # Set the native current-frame value after Cubism's updates so its
        # own parameter restore cannot erase lip sync before the draw call.
        self._model._model.SetParameterValueById(
            "ParamMouthOpenY", self._mouth_open * 2.1)
        if self._line_eye_active:
            # `eyeclose.exp3.json` is an additive Param40=-1 expression. It
            # must be written into the current native frame after
            # Blink/Physics. LAppModel.SetParameterValue saves the base value,
            # whereas this direct API affects the draw about to happen.
            self._model._model.SetParameterValueById("Param40", -1.0)
        self.mouth_pose_changed.emit(self._mouth_open, x, y)

    def _update_lipsync(self) -> None:
        if not self._speaking:
            return
        if self._lipsync is not None and self._lipsync.Update():
            # RMS tracks the actual audio amplitude; a small floor keeps
            # quiet consonants visible without exaggerating silence.
            value = min(1.0, 0.12 + self._lipsync.GetRms() * 8.0)
        elif self._lipsync is not None:
            value = 0.0
        else:
            elapsed = time.monotonic() - self._speech_started_at
            # A pronounced but still natural visible range for text-only
            # dialogue and WAV-read failures.
            value = 0.12 + 0.88 * abs(math.sin(elapsed * 8.2))
        self._mouth_open = min(value, 1.0)


class Live2DWindow(PetWindow):
    """PetWindow-compatible Live2D renderer with static-window interactions."""

    live2d_failed = Signal(str)
    _base_size = (720, 1040)

    def __init__(self, char_data, model_path: Path, scale_override: float = None, parent=None):
        self._live2d_model_path = Path(model_path)
        super().__init__(char_data, scale_override, parent)
        self._label.initialization_failed.connect(self.live2d_failed.emit)
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(50)
        self._cursor_timer.timeout.connect(self._follow_cursor)
        self._cursor_timer.start()
        # Keep the visible mouth moving even if Windows throttles the
        # QOpenGLWidget render timer while the desktop pet is unobstructed.
        self._mouth_timer = QTimer(self)
        self._mouth_timer.setInterval(80)
        self._mouth_timer.timeout.connect(self._advance_mouth_overlay)
        self._mouth_started_at = 0.0
        self._idle_expression_timer = QTimer(self)
        self._idle_expression_timer.setSingleShot(True)
        self._idle_expression_timer.timeout.connect(self._play_idle_line_eye_reaction)
        self._resize_live2d()

    def _setup_labels(self) -> None:
        self._label = Live2DCanvas(self._live2d_model_path, self)
        self._label.installEventFilter(self)
        self.setCentralWidget(self._label)
        self._overlay = MouthOverlay(self._label)
        self._overlay.setGeometry(self._label.rect())
        self._overlay.raise_()
        self._label.mouth_pose_changed.connect(self._overlay.set_pose)

    def _setup_animator(self) -> None:
        # Live2D supplies its own frame updates, breathing, and blinking.
        self._animator = None
        self._pending_scale = None

    def _load_sprites(self) -> None:
        self._pixmaps = []

    def _show_sprite(self) -> None:
        pass

    def set_state(self, state: str) -> None:
        # The model has no motion groups, but its bundled expressions map to
        # the semantic states the rest of Moepet already emits.
        self._frame_state = state
        expressions = {
            "idle": "", "think": "quanquan", "thinking": "quanquan",
            "puzzled": "quanquan", "sad": "tears", "concern": "tears",
            # The authored closed-eye line reaction is used sparingly for
            # acknowledgements. The unrelated `white` expression is unused.
            "embarrassed": "tears", "happy": "eyeclose",
            "content": "eyeclose", "speak": "",
        }
        # Speaking is an overlay state: keep the expression selected for the
        # reply while lipsync animates the mouth.  Clearing it here used to
        # erase ``white`` immediately after a response was classified.
        if state != "speak":
            expression = expressions.get(state, "")
            self._label.set_expression(expression)
            if hasattr(self._label, "set_line_eye_active"):
                self._label.set_line_eye_active(expression == "eyeclose")
            # Expressions are reactions, not a replacement for the model's
            # natural auto-blink. Dazed thinking and line-eye acknowledgements
            # occasionally linger so they are perceptible in a conversation.
            if state in {"think", "thinking", "puzzled"}:
                Live2DWindow._clear_expression_after(
                    self, expression, random.randint(1500, 2800))
            elif state in {"happy", "content"}:
                Live2DWindow._clear_expression_after(
                    self, expression, random.randint(1600, 2600))
        self._label.set_speaking(state == "speak")
        if state == "speak":
            self._mouth_started_at = time.monotonic()
            self._mouth_timer.start()
            self._advance_mouth_overlay()
        else:
            self._mouth_timer.stop()
            self._overlay.set_pose(0.0, *self._label._drag_target)
        idle_expression_timer = getattr(self, "_idle_expression_timer", None)
        if state == "idle" and idle_expression_timer is not None:
            self._schedule_idle_line_eye_reaction()
        elif idle_expression_timer is not None:
            idle_expression_timer.stop()

    def _clear_expression_after(self, expression: str, delay_ms: int) -> None:
        if not expression:
            return

        def clear_if_unchanged() -> None:
            if getattr(self._label, "_expression", None) == expression:
                self._label.set_expression("", force=True)
                if expression == "eyeclose" and hasattr(self._label, "set_line_eye_active"):
                    self._label.set_line_eye_active(False)

        QTimer.singleShot(delay_ms, clear_if_unchanged)

    def _schedule_idle_line_eye_reaction(self) -> None:
        """Let the resting model occasionally make a visible line-eye face."""
        self._idle_expression_timer.start(random.randint(9000, 16000))

    def _play_idle_line_eye_reaction(self) -> None:
        if self._frame_state != "idle" or not self.isVisible():
            return
        self._label.set_expression("eyeclose", force=True)
        self._label.set_line_eye_active(True)

        def restore_idle() -> None:
            if self._frame_state == "idle":
                self._label.set_expression("", force=True)
                self._label.set_line_eye_active(False)
                self._schedule_idle_line_eye_reaction()

        QTimer.singleShot(random.randint(1600, 2600), restore_idle)

    def set_sprite_by_name(self, name: str) -> None:
        pass

    def next_sprite(self) -> None:
        pass

    def play_animation(self, anim_type: str) -> None:
        pass

    def _is_head_point(self, point) -> bool:
        return False

    def _is_model_point(self, point) -> bool:
        """Accept only Cubism drawables, never their transparent bounds."""
        model = getattr(self._label, "_model", None)
        if model is not None:
            try:
                # HitPart uses broad authored part bounds.  HitDrawable tests
                # the rendered mesh itself, so it correctly rejects the large
                # transparent area around Noir's artboard.
                return bool(model._model.HitDrawable(
                    float(point.x()), float(point.y()), False))
            except Exception:
                # Never widen interaction to the entire transparent widget if
                # the renderer is still initializing or a model is malformed.
                return False
        return False

    def mouseDoubleClickEvent(self, event) -> None:
        """Only the rendered Live2D body, not its transparent window, opens chat."""
        if event.button() == Qt.LeftButton and not self._is_model_point(event.position()):
            self._click_timer.stop()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        """Keep desktop clicks through the transparent Live2D artboard unblocked."""
        if not self._is_model_point(event.pos()):
            event.accept()
            return
        self._menu.exec(event.globalPos())

    def _show_head_touch_expression(self) -> bool:
        return False

    def rescale(self, scale: float) -> None:
        self._scale = float(scale)
        self._resize_live2d()

    def set_always_on_top(self, enabled: bool) -> None:
        # Reapplying identical flags recreates the OpenGL host on Windows.
        # A new Live2D window is already created with the enabled flag.
        current = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
        if current != bool(enabled):
            super().set_always_on_top(enabled)

    def _resize_live2d(self) -> None:
        width = max(280, round(self._base_size[0] * self._scale))
        height = max(400, round(self._base_size[1] * self._scale))
        self.resize(width, height)
        # This model's artboard has generous transparent padding.
        self._label.set_model_scale(1.65)
        self._overlay.setGeometry(self._label.rect())
        self._overlay.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_overlay"):
            self._overlay.setGeometry(self._label.rect())
            self._overlay.raise_()

    def _follow_cursor(self) -> None:
        """Map the desktop pointer to the Live2D drag space at 20 FPS."""
        if not self.isVisible() or self.width() <= 0 or self.height() <= 0:
            return
        cursor = QCursor.pos()
        center = self.frameGeometry().center()
        x = (cursor.x() - center.x()) / max(1.0, self.width() * 0.8)
        y = (center.y() - cursor.y()) / max(1.0, self.height() * 0.8)
        self._label.set_drag_target(x, y)
        if not self._mouth_timer.isActive():
            self._overlay.set_pose(0.0, x, y)

    def _advance_mouth_overlay(self) -> None:
        """Animate the visible speech mouth independently from OpenGL ticks."""
        if not self._mouth_timer.isActive():
            return
        elapsed = time.monotonic() - self._mouth_started_at
        # A full open-close cycle takes ~0.36 seconds, which remains readable
        # at the configured 50% desktop-pet scale.
        openness = 0.16 + 0.84 * abs(math.sin(elapsed * 8.7))
        self._label.set_visual_mouth_open(openness)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._cursor_timer.start()
        self._label.set_rendering_enabled(True)
        if getattr(self, "_frame_state", "") == "speak":
            self._mouth_timer.start()

    def hideEvent(self, event) -> None:
        self._label.set_rendering_enabled(False)
        self._cursor_timer.stop()
        self._mouth_timer.stop()
        super().hideEvent(event)

    def start_lipsync(self, audio_path: str) -> None:
        self._label.start_lipsync(audio_path)
