from pathlib import Path
import json
import os

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QPushButton

from core.character import CharacterLoader
from core.config import Config
from pet_manager import PetManager
from core.knowledge_base import KnowledgeBase


@pytest.fixture(scope="session")
def qapp():
    """Provide one offscreen Qt application for widget tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def test_character_config_keeps_its_own_prompt(tmp_path):
    char_dir = tmp_path / "pet"
    char_dir.mkdir(parents=True)
    (char_dir / "config.json").write_text(json.dumps({
        "name": "Pet",
        "character_prompt": {"system_prompt": "pet-only", "format_prompt": ""},
    }), encoding="utf-8")
    data = CharacterLoader(tmp_path).load("pet")
    assert data.character_prompt["system_prompt"] == "pet-only"


def test_expression_selector_prefers_the_reply_then_user_context():
    from core.expression import select_expression

    assert select_expression("太好了，我也很高兴。") == "happy"
    assert select_expression("我想想看。", "今天好开心") == "thinking"
    assert select_expression("我会陪着你。", "我今天很难过") == "sad"
    assert select_expression("别勉强自己，休息一下。") == "concern"
    assert select_expression("这件事有点奇怪。") == "puzzled"
    assert select_expression("恭喜，一切都很顺利。") == "happy"


def test_character_resolves_configured_expression_sprite(tmp_path):
    char_dir = tmp_path / "pet"
    char_dir.mkdir()
    (char_dir / "config.json").write_text(json.dumps({
        "name": "Pet", "sprites": {"idle": "idle.png", "happy": "smile.png"},
    }), encoding="utf-8")
    data = CharacterLoader(tmp_path).load("pet")
    assert data.sprite_for_expression("happy") == "smile"
    assert data.sprite_for_expression("missing") == "idle"


def test_character_resolves_configured_blink_sprite(tmp_path):
    char_dir = tmp_path / "pet"
    char_dir.mkdir()
    (char_dir / "config.json").write_text(json.dumps({
        "name": "Pet", "blinks": {"idle": "idle_closed.png"},
    }), encoding="utf-8")
    data = CharacterLoader(tmp_path).load("pet")
    assert data.blink_for_sprite("idle") == "idle_closed"
    assert data.blink_for_sprite("happy") == ""


def test_character_loads_head_touch_only_sprites(tmp_path):
    char_dir = tmp_path / "pet"
    char_dir.mkdir()
    (char_dir / "config.json").write_text(json.dumps({
        "name": "Pet",
        "interactions": {"head_touch": ["messy.png", "flustered.png"]},
    }), encoding="utf-8")
    data = CharacterLoader(tmp_path).load("pet")
    assert data.head_touch_sprite_names() == ["messy", "flustered"]


def test_portraits_are_normalized_to_one_character_size_and_anchor(qapp):
    from PySide6.QtGui import QPainter, QPixmap
    from core.sprite_normalizer import common_layout, normalize_portrait, opaque_bounds

    def portrait(width, height, rect):
        pm = QPixmap(width, height)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.fillRect(*rect, Qt.white)
        painter.end()
        return pm

    regular = portrait(900, 1500, (100, 184, 743, 1271))
    small_high = portrait(825, 1500, (96, 233, 668, 1144))
    layout = common_layout([regular, regular, small_high])
    outputs = [normalize_portrait(pm, layout) for pm in (regular, small_high)]
    bounds = [opaque_bounds(pm) for pm in outputs]

    assert all(pm.size() == outputs[0].size() for pm in outputs)
    assert all(rect.height() == bounds[0].height() for rect in bounds)
    assert all(rect.bottom() == bounds[0].bottom() for rect in bounds)


def test_role_switch_saves_old_history_and_loads_new_history(tmp_path):
    class Window:
        def hide(self):
            pass

        def show(self):
            pass

        def set_character_menu(self, *_args):
            pass

    class Llm:
        def __init__(self):
            self.cancelled = False
            self.cleared = False

        def cancel(self):
            self.cancelled = True

        def clear_history(self):
            self.cleared = True

    manager = type("Manager", (), {})()
    manager.config = Config(tmp_path / "config.json")
    manager.config.set("current_character", "old")
    manager._llm = Llm()
    manager._windows = {"old": Window(), "new": Window()}
    manager._char_data = {}
    manager._switch_character = lambda _name: None
    manager._dialog = None
    manager._tray = None
    manager._cancel_role_async_work = lambda: events.append("cancel-async")
    events = []
    manager._save_chat_history = lambda: events.append("save-old")
    manager._load_knowledge_base = lambda: events.append("load-knowledge")
    manager._load_chat_history = lambda: events.append("load-new")

    PetManager._switch_character(manager, "new")

    assert manager.config.current_character == "new"
    assert manager._llm.cancelled and manager._llm.cleared
    assert events == ["cancel-async", "save-old", "load-knowledge", "load-new"]


def test_config_has_multimodal_defaults(tmp_path):
    config = Config(tmp_path / "config.json")
    assert config.get("asr", "compute_type") == "int8"
    assert config.get("screen_capture", "keep_captures") is False
    assert config.get("screen_capture", "auto_observe") is False
    assert config.get("screen_capture", "observe_min_interval") == 300
    assert config.get("screen_capture", "vision_max_dimension") == 1280


def test_cloud_asr_endpoint_is_completed(tmp_path):
    from core.asr_service import ASRService
    service = ASRService()
    assert service.transcribe_cloud(tmp_path / "missing.wav", "", "", "whisper-1") is False


def test_background_services_expose_their_busy_state():
    from core.asr_service import ASRService
    service = ASRService()
    assert service.is_busy() is False


def test_unconfigured_asr_does_not_start_microphone_or_register_hotkey(tmp_path):
    manager = type("Manager", (), {})()
    manager.config = Config(tmp_path / "config.json")
    manager.config.set("asr", "enabled", True)
    manager.config.set("asr", "provider", "cloud")
    manager.config.set("asr", "base_url", "")
    manager._asr = type("Asr", (), {"is_busy": lambda self: False})()
    manager._voice_recorder = type("Recorder", (), {
        "start": lambda self: (_ for _ in ()).throw(AssertionError("microphone started")),
    })()
    manager._dialog = None
    PetManager._start_voice_input(manager)


def test_llm_response_cleaning_removes_stage_directions_and_markup():
    from core.llm_service import LLMService
    service = LLMService()
    service.configure("http://localhost:1", "", "test")
    text = "<think>reasoning</think>你好呀。（偏着头）\n动作：轻轻挥手"
    assert service._clean_response(text) == "你好呀。"


def test_tts_error_is_logged_without_writing_to_chat(caplog):
    manager = type("Manager", (), {})()
    manager._tts_epoch = 0
    manager._role_epoch = 0
    manager._dialog = type("Dialog", (), {
        "display_text": lambda *_args: (_ for _ in ()).throw(AssertionError("chat was changed")),
    })()
    manager._set_pet_state = lambda _state: None
    PetManager._on_tts_error(manager, "HTTP Error 404")
    assert "TTS synthesis failed: HTTP Error 404" in caplog.text


def test_tts_failure_reveals_a_reply_waiting_for_audio():
    manager = type("Manager", (), {})()
    manager._tts_epoch = manager._role_epoch = 0
    manager._pending_tts_epoch = 0
    manager._pending_tts_text = "等待语音的回复"
    displayed = []
    manager._dialog = type("Dialog", (), {
        "display_text": lambda _self, text, role: displayed.append((text, role)),
    })()
    manager._set_pet_state = lambda _state: None
    manager._show_pending_tts_text = lambda: PetManager._show_pending_tts_text(manager)
    PetManager._on_tts_error(manager, "HTTP Error 500")
    assert displayed == [("等待语音的回复", "assistant")]


def test_audio_sync_does_not_display_stream_chunks():
    manager = type("Manager", (), {})()
    received = []
    manager._dialog = type("Dialog", (), {
        "append_stream": lambda _self, text: received.append(text),
    })()
    manager._should_sync_text_to_audio = lambda: True
    PetManager._on_llm_chunk(manager, "不应提前显示")
    assert received == []


def test_audio_sync_requires_a_successful_tts_request(tmp_path):
    manager = type("Manager", (), {})()
    manager.config = Config(tmp_path / "config.json")
    manager.config.set("tts", "enabled", True)
    manager.config.set("tts", "auto_play", True)
    manager._tts_available = False
    assert not PetManager._should_sync_text_to_audio(manager)
    manager._tts_available = True
    assert PetManager._should_sync_text_to_audio(manager)


def test_remote_audio_services_require_a_key_without_starting_work(tmp_path):
    from core.asr_service import ASRService
    from core.tts_service import TTSService
    asr = ASRService()
    tts = TTSService()
    assert asr.transcribe_cloud(tmp_path / "missing.wav", "https://api.example/v1", "", "whisper-1") is False
    assert tts.synthesize_cloud("hello", "https://api.example/v1", "", "tts-1", "alloy", tmp_path / "out.wav") is False


def test_gpt_sovits_endpoint_uses_service_root_not_openai_v2_path():
    from core.tts_service import TTSService
    assert TTSService._tts_url("https://tts.example:8443/v2") == "https://tts.example:8443/tts"
    assert TTSService._tts_url("https://tts.example:8443") == "https://tts.example:8443/tts"


def test_tts_player_uses_qt_objects_without_a_non_qt_parent():
    source = Path("pet_manager.py").read_text(encoding="utf-8")
    assert "QAudioOutput()" in source
    assert "QMediaPlayer()" in source


def test_live2d_receives_speak_state_while_static_portraits_keep_their_frame(tmp_path, monkeypatch):
    import pet_manager as pet_manager_module

    class LiveWindow:
        def __init__(self): self.states = []
        def set_state(self, state): self.states.append(state)

    class StaticWindow:
        def __init__(self): self.states = []
        def set_state(self, state): self.states.append(state)
        def set_sprite_by_name(self, _name): pass

    monkeypatch.setattr(pet_manager_module, "Live2DWindow", LiveWindow)
    manager = type("Manager", (), {})()
    manager.config = Config(tmp_path / "config.json")
    manager.config.set("current_character", "noir")
    manager._char_data = {}
    manager._windows = {"noir": LiveWindow()}
    PetManager._set_pet_state(manager, "speak")
    assert manager._windows["noir"].states == ["speak"]

    manager._windows = {"noir": StaticWindow()}
    PetManager._set_pet_state(manager, "speak")
    assert manager._windows["noir"].states == []


def test_live2d_routes_reply_expression_to_the_model_state(tmp_path, monkeypatch):
    import pet_manager as pet_manager_module

    class LiveWindow:
        def __init__(self): self.states = []
        def set_state(self, state): self.states.append(state)

    monkeypatch.setattr(pet_manager_module, "Live2DWindow", LiveWindow)
    monkeypatch.setattr(pet_manager_module, "select_expression", lambda *_args: "content")
    manager = type("Manager", (), {})()
    manager.config = Config(tmp_path / "config.json")
    manager.config.set("current_character", "noir")
    manager._char_data = {"noir": object()}
    manager._windows = {"noir": LiveWindow()}
    manager._last_user_text = ""

    PetManager._show_reply_expression(manager, "ok")
    assert manager._windows["noir"].states == ["content"]


def test_live2d_uses_line_eye_reaction_for_a_happy_reply(tmp_path, monkeypatch):
    import pet_manager as pet_manager_module

    class LiveWindow:
        def __init__(self): self.states = []
        def set_state(self, state): self.states.append(state)

    monkeypatch.setattr(pet_manager_module, "Live2DWindow", LiveWindow)
    monkeypatch.setattr(pet_manager_module, "select_expression", lambda *_args: "happy")
    manager = type("Manager", (), {})()
    manager.config = Config(tmp_path / "config.json")
    manager.config.set("current_character", "noir")
    manager._char_data = {"noir": object()}
    manager._windows = {"noir": LiveWindow()}
    manager._last_user_text = ""

    PetManager._show_reply_expression(manager, "happy reply")
    assert manager._windows["noir"].states == ["happy"]


def test_live2d_text_reply_starts_a_speaking_turn_without_tts(tmp_path, monkeypatch):
    import pet_manager as pet_manager_module

    class LiveWindow:
        def __init__(self): self.states = []
        def set_state(self, state): self.states.append(state)

    monkeypatch.setattr(pet_manager_module, "Live2DWindow", LiveWindow)
    scheduled = []
    monkeypatch.setattr(pet_manager_module.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    manager = type("Manager", (), {})()
    manager.config = Config(tmp_path / "config.json")
    manager.config.set("current_character", "noir")
    manager._role_epoch = 0
    manager._windows = {"noir": LiveWindow()}
    manager._show_reply_expression = lambda text: manager._windows["noir"].states.append(f"expression:{text}")

    PetManager._animate_text_speech(manager, "你好")
    assert manager._windows["noir"].states == ["speak"]
    assert scheduled[0][0] == 1100
    scheduled[0][1]()
    assert manager._windows["noir"].states == ["speak", "expression:你好"]


def test_live2d_advance_passes_the_frame_delta_to_the_native_model():
    from ui.live2d_window import Live2DCanvas

    calls = []

    class NativeModel:
        def LoadParameters(self): calls.append("load")
        def UpdateMotion(self, value): calls.append(("motion", value))
        def SaveParameters(self): calls.append("save")
        def UpdateBlink(self, value): calls.append(("blink", value))
        def UpdateExpression(self, value): calls.append(("expression", value))
        def UpdateDrag(self, value): calls.append(("drag", value))
        def UpdateBreath(self, value): calls.append(("breath", value))
        def UpdatePhysics(self, value): calls.append(("physics", value))
        def UpdatePose(self, value): calls.append(("pose", value))
        def Update(self, value): calls.append(("update", value))
        def SetParameterValueById(self, *_args): calls.append("mouth")

    class Model:
        _model = NativeModel()
        def Drag(self, *_args): calls.append("target")
        def SetParameterValue(self, *_args): pass

    canvas = Live2DCanvas(Path("model3.json"))
    canvas._model = Model()
    canvas._update_lipsync = lambda: calls.append("lipsync")
    canvas._advance_model(0.033)
    assert calls[-2] == ("update", 0.033)
    assert calls[-1] == "mouth"


def test_live2d_applies_mouse_and_closed_mouth_parameters_after_physics():
    from ui.live2d_window import Live2DCanvas

    applied = []

    class NativeModel:
        def SetParameterValueById(self, parameter, value): applied.append((parameter, value))
    class Model:
        _model = NativeModel()
        def SetParameterValue(self, parameter, value):
            applied.append((parameter, value))

    canvas = Live2DCanvas(Path("model3.json"))
    canvas._model = Model()
    canvas._drag_target = (0.5, -0.25)
    canvas._mouth_open = 0.0
    canvas._apply_visible_parameters()

    assert applied == [
        ("ParamAngleX", 15.0),
        ("ParamAngleY", -4.5),
        ("ParamEyeBallX", -0.5),
        ("ParamEyeBallY", -0.25),
        ("ParamMouthOpenY", 0.0),
    ]


def test_live2d_keeps_the_line_eye_parameter_after_auto_updates():
    from ui.live2d_window import Live2DCanvas

    applied = []
    class NativeModel:
        def SetParameterValueById(self, parameter, value): applied.append((parameter, value))
    class Model:
        _model = NativeModel()
        def SetParameterValue(self, parameter, value): applied.append((parameter, value))

    canvas = Live2DCanvas(Path("model3.json"))
    canvas._model = Model()
    canvas._line_eye_active = True
    canvas._apply_visible_parameters()
    assert applied[-1] == ("Param40", -1.0)


def test_dialog_position_is_persisted_relative_to_the_active_pet(tmp_path):
    manager = type("Manager", (), {})()
    manager.config = Config(tmp_path / "config.json")
    manager.config.set("current_character", "noir")
    pet = type("Pet", (), {"x": lambda self: 1000, "y": lambda self: 400})()
    manager._windows = {"noir": pet}

    PetManager._save_dialog_offset(manager, 1012, 155)
    assert manager.config.get("dialog", "offset_x") == 12
    assert manager.config.get("dialog", "offset_y") == -245


def test_visible_dialog_moves_with_the_pet_using_saved_offset(tmp_path):
    class Pet:
        def x(self): return 600
        def y(self): return 300
        def width(self): return 360
    class Dialog:
        def __init__(self): self.moves = []
        def isVisible(self): return True
        def move(self, x, y): self.moves.append((x, y))
        def width(self): return 480
        def height(self): return 240

    manager = type("Manager", (), {})()
    manager.config = Config(tmp_path / "config.json")
    manager.config.set("current_character", "noir")
    manager.config.set("dialog", "offset_x", 8)
    manager.config.set("dialog", "offset_y", -220)
    manager._windows = {"noir": Pet()}
    manager._dialog = Dialog()
    manager._dialog_offset_for = lambda _win: PetManager._dialog_offset_for(manager, _win)
    PetManager._move_dialog_with_pet(manager)
    assert manager._dialog.moves == [(608, 80)]


def test_start_keeps_settings_closed_even_when_chat_is_unconfigured(tmp_path):
    manager = type("Manager", (), {})()
    manager.config = Config(tmp_path / "config.json")
    manager.config.set("current_character", "noir")
    manager._windows = {"noir": type("Window", (), {
        "move": lambda self, *_args: None, "show": lambda self: None,
    })()}
    manager._setup_tray = lambda: None
    manager._needs_initial_setup = lambda: True
    manager._open_settings = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("settings opened during startup"))

    PetManager.start(manager)
    assert manager.config.get("dialog", "visible") is False


def test_live2d_uses_the_model_dazed_expression_for_thinking_states():
    from ui.live2d_window import Live2DWindow

    class Canvas:
        def __init__(self):
            self.expression = self.speaking = None
            self._drag_target = (0.0, 0.0)
        def set_expression(self, expression): self.expression = expression
        def set_speaking(self, speaking): self.speaking = speaking

    timer = type("Timer", (), {"stop": lambda self: None})()
    overlay = type("Overlay", (), {"set_pose": lambda self, *_args: None})()
    window = type("Window", (), {
        "_label": Canvas(), "_mouth_timer": timer, "_overlay": overlay,
    })()
    Live2DWindow.set_state(window, "think")
    assert window._label.expression == "quanquan"
    assert window._label.speaking is False


def test_live2d_speaking_keeps_the_line_eye_reply_reaction_visible():
    from ui.live2d_window import Live2DWindow

    class Canvas:
        def __init__(self):
            self.expressions = []
            self._drag_target = (0.0, 0.0)
        def set_expression(self, expression): self.expressions.append(expression)
        def set_speaking(self, _speaking): pass

    timer = type("Timer", (), {"start": lambda self: None, "stop": lambda self: None})()
    overlay = type("Overlay", (), {"set_pose": lambda self, *_args: None})()
    window = type("Window", (), {
        "_label": Canvas(), "_mouth_timer": timer, "_overlay": overlay,
        "_mouth_started_at": 0.0, "_advance_mouth_overlay": lambda self: None,
    })()
    Live2DWindow.set_state(window, "content")
    Live2DWindow.set_state(window, "speak")
    assert window._label.expressions == ["eyeclose"]


def test_live2d_idle_line_eye_reaction_enables_the_frame_parameter(monkeypatch):
    import ui.live2d_window as live2d_window_module
    from ui.live2d_window import Live2DWindow

    scheduled = []
    monkeypatch.setattr(live2d_window_module.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    monkeypatch.setattr(live2d_window_module.random, "randint", lambda _low, _high: 1600)

    class Canvas:
        def __init__(self): self.calls = []
        def set_expression(self, expression, force=False): self.calls.append(("expression", expression, force))
        def set_line_eye_active(self, active): self.calls.append(("line", active))

    window = type("Window", (), {
        "_frame_state": "idle", "_label": Canvas(), "isVisible": lambda self: True,
        "_schedule_idle_line_eye_reaction": lambda self: None,
    })()
    Live2DWindow._play_idle_line_eye_reaction(window)
    assert window._label.calls[:2] == [("expression", "eyeclose", True), ("line", True)]
    assert scheduled[0][0] == 1600




def test_live2d_model_hit_uses_cubism_drawable_meshes_not_part_bounds():
    from PySide6.QtCore import QPointF
    from ui.live2d_window import Live2DWindow

    class NativeModel:
        def HitDrawable(self, x, y, top_only):
            return ["ArtMesh"] if (x, y, top_only) == (180.0, 280.0, False) else []

    class Model:
        _model = NativeModel()

    window = type("Window", (), {
        "width": lambda self: 360,
        "height": lambda self: 520,
        "_label": type("Canvas", (), {"_model": Model()})(),
    })()
    assert Live2DWindow._is_model_point(window, QPointF(180, 280))
    assert not Live2DWindow._is_model_point(window, QPointF(8, 8))


def test_live2d_context_menu_ignores_transparent_artboard_padding(qapp):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QContextMenuEvent
    from ui.live2d_window import Live2DWindow

    opened = []
    window = type("Window", (), {
        "_is_model_point": lambda _self, point: point.x() > 20,
        "_menu": type("Menu", (), {"exec": lambda _self, point: opened.append(point)})(),
    })()
    empty_event = QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(8, 8), QPoint(8, 8))
    Live2DWindow.contextMenuEvent(window, empty_event)
    body_event = QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(80, 80), QPoint(80, 80))
    Live2DWindow.contextMenuEvent(window, body_event)
    assert opened == [QPoint(80, 80)]


def test_live2d_draws_a_visible_mouth_overlay_at_pet_scale(qapp, tmp_path):
    from ui.live2d_window import MouthOverlay

    overlay = MouthOverlay()
    overlay.resize(360, 520)
    overlay.set_pose(1.0, 0.0, 0.0)
    # The fallback mouth is centered near the model face and must remain
    # visible even when the authored texture mouth is only a few pixels wide.
    assert overlay._openness == 1.0


def test_live2d_mouth_overlay_uses_its_own_timer(qapp, tmp_path):
    from ui.live2d_window import Live2DWindow

    class Canvas:
        _drag_target = (0.0, 0.0)
        def set_expression(self, _expression): pass
        def set_speaking(self, _speaking): pass
        def set_visual_mouth_open(self, openness): self.openness = openness

    window = type("Window", (), {
        "_label": Canvas(), "_mouth_started_at": 0.0,
        "_mouth_timer": type("Timer", (), {"isActive": lambda self: True})(),
    })()
    Live2DWindow._advance_mouth_overlay(window)
    assert window._label.openness > 0.1


def test_frame_animation_and_single_png_fallback(tmp_path):
    character_dir = tmp_path / "pet"
    sprites = character_dir / "sprites"
    sprites.mkdir(parents=True)
    (character_dir / "config.json").write_text(json.dumps({"name": "Pet"}), encoding="utf-8")
    (character_dir / "animations.json").write_text(json.dumps({
        "idle": {"frames": ["idle.png"], "frame_ms": 100, "loop": True}
    }), encoding="utf-8")
    data = CharacterLoader(tmp_path).load("pet")
    assert data.animations["idle"].frames == ["idle.png"]
    assert data.animations["idle"].frame_ms == 100


def test_single_frame_idle_state_starts_blinking(qapp, tmp_path):
    from PySide6.QtGui import QPainter, QPixmap
    from ui.pet_window import PetWindow

    char_dir = tmp_path / "pet"
    sprites = char_dir / "sprites"
    sprites.mkdir(parents=True)
    for name in ("idle", "closed"):
        pm = QPixmap(100, 200)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.fillRect(20, 20, 60, 170, Qt.white)
        painter.end()
        pm.save(str(sprites / f"{name}.png"))
    (char_dir / "config.json").write_text(json.dumps({
        "name": "Pet", "blinks": {"idle": "closed.png"},
    }), encoding="utf-8")
    (char_dir / "animations.json").write_text(json.dumps({
        "idle": {"frames": ["idle.png"], "frame_ms": 100, "loop": True},
    }), encoding="utf-8")
    window = PetWindow(CharacterLoader(tmp_path).load("pet"), scale_override=1.0)
    window.set_state("idle")
    assert window._blink_timer.isActive()
    assert not window._frame_timer.isActive()


def test_window_starts_on_the_configured_idle_sprite(qapp, tmp_path):
    from PySide6.QtGui import QPainter, QPixmap
    from ui.pet_window import PetWindow

    char_dir = tmp_path / "pet"
    sprites = char_dir / "sprites"
    sprites.mkdir(parents=True)
    for name in ("angry", "neutral", "closed"):
        pm = QPixmap(100, 200)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.fillRect(20, 20, 60, 170, Qt.white)
        painter.end()
        pm.save(str(sprites / f"{name}.png"))
    (char_dir / "config.json").write_text(json.dumps({
        "name": "Pet",
        "sprites": {"idle": "neutral.png"},
        "blinks": {"neutral": "closed.png"},
    }), encoding="utf-8")
    window = PetWindow(CharacterLoader(tmp_path).load("pet"), scale_override=1.0)
    assert window._current_sprite_name == "neutral"
    assert window._blink_timer.isActive()


def test_portrait_double_click_toggles_dialog_without_sprite_action(qapp, tmp_path):
    from ui.pet_window import PetWindow
    char_dir = tmp_path / "pet"
    sprites = char_dir / "sprites"
    sprites.mkdir(parents=True)
    (char_dir / "config.json").write_text(json.dumps({"name": "Pet"}), encoding="utf-8")
    window = PetWindow(CharacterLoader(tmp_path).load("pet"))
    toggles = []
    signals = __import__("core.signals", fromlist=["signals"]).signals
    signals.dialog_toggle_requested.connect(lambda: toggles.append(True))
    window._click_timer.start()
    event = QMouseEvent(QMouseEvent.MouseButtonDblClick, QPoint(1, 1), QPoint(1, 1),
                        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    window.mouseDoubleClickEvent(event)
    assert toggles == [True]
    assert not window._click_timer.isActive()


def test_head_touch_hitbox_and_manual_cycle_exclude_special_sprites(qapp, tmp_path):
    from PySide6.QtGui import QPainter, QPixmap
    from ui.pet_window import PetWindow

    char_dir = tmp_path / "pet"
    sprites = char_dir / "sprites"
    sprites.mkdir(parents=True)
    for name in ("normal", "happy", "messy"):
        pm = QPixmap(100, 200)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.fillRect(20, 20, 60, 170, Qt.white)
        painter.end()
        pm.save(str(sprites / f"{name}.png"))
    (char_dir / "config.json").write_text(json.dumps({
        "name": "Pet",
        "sprites": {"idle": "normal.png", "happy": "happy.png"},
        "interactions": {"head_touch": ["messy.png"]},
    }), encoding="utf-8")

    window = PetWindow(CharacterLoader(tmp_path).load("pet"), scale_override=1.0)
    normal = next(i for i, info in enumerate(window.char_data.sprites) if info.name == "normal")
    window._current_index = normal
    window._current_sprite_name = "normal"
    assert window._is_head_point(QPoint(50, 30))
    assert not window._is_head_point(QPoint(50, 150))

    seen = set()
    for _ in range(5):
        window.next_sprite()
        seen.add(window._current_sprite_name)
    assert "messy" not in seen

    window._click_pos = QPoint(50, 30)
    window._handle_click_action()
    assert window._current_sprite_name == "messy"


def test_body_click_does_not_cycle_to_an_unrelated_expression(qapp, tmp_path):
    from PySide6.QtGui import QPainter, QPixmap
    from ui.pet_window import PetWindow

    char_dir = tmp_path / "pet"
    sprites = char_dir / "sprites"
    sprites.mkdir(parents=True)
    for name in ("angry", "neutral", "closed"):
        pm = QPixmap(100, 200)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.fillRect(20, 20, 60, 170, Qt.white)
        painter.end()
        pm.save(str(sprites / f"{name}.png"))
    (char_dir / "config.json").write_text(json.dumps({
        "name": "Pet",
        "sprites": {"idle": "neutral.png"},
        "blinks": {"neutral": "closed.png"},
    }), encoding="utf-8")
    window = PetWindow(CharacterLoader(tmp_path).load("pet"), scale_override=1.0)
    window._click_pos = QPoint(50, 160)
    window._handle_click_action()
    assert window._current_sprite_name == "neutral"
    assert window._blink_timer.isActive()


def test_start_places_portrait_bottom_right_and_closes_dialog(tmp_path, monkeypatch):
    class Window:
        def __init__(self): self.moves = []
        def width(self): return 100
        def height(self): return 200
        def move(self, x, y): self.moves.append((x, y))
        def show(self): pass
        def x(self): return self.moves[-1][0]
        def y(self): return self.moves[-1][1]
    class Area:
        def right(self): return 1919
        def bottom(self): return 1079
    class Screen:
        def availableGeometry(self): return Area()
    manager = type("Manager", (), {})()
    manager.config = Config(tmp_path / "config.json")
    manager._windows = {"noir": Window()}
    manager._setup_tray = lambda: None
    manager._needs_initial_setup = lambda: False
    monkeypatch.setattr("pet_manager.QApplication.primaryScreen", lambda: Screen())
    PetManager.start(manager)
    assert manager._windows["noir"].moves == [(1105, 364)]
    assert manager.config.get("dialog", "visible") is False


def test_start_restores_saved_portrait_position(tmp_path, monkeypatch):
    class Window:
        def __init__(self): self.moves = []
        def width(self): return 100
        def height(self): return 200
        def move(self, *position): self.moves.append(position)
        def show(self): pass

    manager = type("Manager", (), {})()
    manager.config = Config(tmp_path / "config.json")
    manager.config.save_position("pet", 654, 321)
    manager._windows = {"noir": Window()}
    manager._setup_tray = lambda: None
    manager._needs_initial_setup = lambda: False
    monkeypatch.setattr("pet_manager.QApplication.primaryScreen", lambda: None)
    PetManager.start(manager)
    assert manager._windows["noir"].moves == [(654, 321)]


def test_screen_chat_intent_is_explicit():
    assert PetManager._is_screen_request("请识别屏幕内容")
    assert PetManager._is_screen_request("帮我识图")
    assert not PetManager._is_screen_request("你好，今天怎么样？")


def test_knowledge_import_and_search(tmp_path):
    source = tmp_path / "world.md"
    source.write_text("# 月港\n\n诺瓦在月港经营一家星图店，讨厌谎言。", encoding="utf-8")
    base = KnowledgeBase(tmp_path / "character")
    copied, errors = base.import_files([str(source)], "world")
    assert copied == 1 and not errors
    assert (base.sources_dir / "world" / "world.md").exists()
    assert "月港" in base.search("诺瓦在月港做什么？")[0]["text"]


def test_knowledge_keeps_import_type(tmp_path):
    source = tmp_path / "lines.txt"
    source.write_text("用户：你好\n角色：你好呀", encoding="utf-8")
    base = KnowledgeBase(tmp_path / "character")
    base.import_files([str(source)], "dialogue")
    assert base.search("你好")[0]["type"] == "dialogue"
    assert (base.sources_dir / "dialogue" / "lines.txt").exists()


def test_secret_fallback_can_remain_in_config_when_keyring_is_missing(tmp_path, monkeypatch):
    config = Config(tmp_path / "config.json")
    monkeypatch.setattr(config, "set_secret", lambda _name, _value: False)
    key = "local-development-key"
    settings = {"llm": {"api_key": key}}
    if not config.set_secret("llm", settings["llm"].pop("api_key")):
        settings["llm"]["api_key"] = key
    config.set("llm", "api_key", settings["llm"]["api_key"])
    assert config.get("llm", "api_key") == key


def test_api_key_validation_rejects_pasted_documents():
    assert Config.is_valid_api_key("sk-valid-key-123")
    assert not Config.is_valid_api_key("line one\nline two")
    assert not Config.is_valid_api_key("has a space")


def test_permanent_character_context_is_not_query_dependent(tmp_path):
    source = tmp_path / "profile.md"
    source.write_text("Noir 安静、谨慎，不会刻意卖萌。", encoding="utf-8")
    base = KnowledgeBase(tmp_path / "character")
    base.import_files([str(source)], "character")
    assert "安静、谨慎" in base.permanent_context("character")


def test_config_loads_bom_and_persists_key(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"llm":{"api_key":"sk-persisted-key"}}', encoding="utf-8-sig")
    config = Config(path)
    assert config.get("llm", "api_key") == "sk-persisted-key"
    config.save()
    assert Config(path).get("llm", "api_key") == "sk-persisted-key"


def test_config_migrates_new_provider_secrets(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text('{"asr":{"api_key":"asr-key"},"tts":{"api_key":"tts-key"}}', encoding="utf-8")
    saved = {}
    monkeypatch.setattr(Config, "set_secret", lambda _self, name, value: saved.setdefault(name, value) is not None)
    config = Config(path)
    assert saved == {"asr": "asr-key", "tts": "tts-key"}
    assert config.get("asr", "api_key") == ""
    assert config.get("tts", "api_key") == ""


def test_screen_observer_clamps_intervals():
    from core.screen_observer import ScreenObserver
    observer = ScreenObserver()
    observer.configure(False, 1, 2)
    assert observer._min_seconds == 60
    assert observer._max_seconds == 60


def test_screen_observer_does_not_restart_after_stop():
    from core.screen_observer import ScreenObserver
    observer = ScreenObserver()
    observer.configure(True, 60, 60)
    assert observer._enabled is True
    observer.stop()
    observer.schedule_next()
    assert observer._enabled is False
    assert not observer._timer.isActive()


def test_llm_excludes_transient_turns_from_saved_history():
    from core.llm_service import LLMService
    service = LLMService()
    service.add_user_message("normal turn")
    service.add_user_message("internal observation instruction", persist=False)
    service.add_assistant_message("reply")
    assert service.history == [
        {"role": "user", "content": "normal turn"},
        {"role": "assistant", "content": "reply"},
    ]


def test_cloud_service_readiness_requires_credentials(tmp_path):
    from ui.settings.service_status import asr_ready, tts_ready
    config = Config(tmp_path / "config.json")
    config.set("asr", "enabled", True)
    config.set("asr", "provider", "cloud")
    config.set("asr", "base_url", "https://example.test")
    config.set("asr", "model", "whisper-1")
    config.set("tts", "enabled", True)
    config.set("tts", "provider", "gpt_sovits_remote")
    config.set("tts", "base_url", "https://example.test")
    config.set("tts", "remote_reference_audio", "/models/noir/reference.ogg")
    assert not asr_ready(config)
    assert not tts_ready(config)


def test_settings_persistence_preserves_existing_provider_secret(tmp_path, monkeypatch):
    from ui.settings.persistence import apply_settings
    config = Config(tmp_path / "config.json")
    monkeypatch.setattr(config, "get_secret", lambda section: "stored-key" if section == "asr" else "")
    payload, error = apply_settings(config, {"asr": {"enabled": True, "api_key": ""}})
    assert error is None
    assert payload["asr"]["api_key"] == "stored-key"
    assert config.get("asr", "api_key") == "stored-key"


def test_llm_post_processing_can_be_strict_or_tolerant():
    from core.llm_service import LLMService
    service = LLMService()
    service.configure("https://example.test", "key", "model", r"<meta>.*?</meta>")
    assert service._clean_response("ok<meta>hidden</meta>") == "ok"
    service.configure("https://example.test", "key", "model", "[", ignore_format_error=True)
    assert service._clean_response("keep this") == "keep this"
    service.configure("https://example.test", "key", "model", "[", ignore_format_error=False)
    import pytest
    with pytest.raises(ValueError):
        service._clean_response("must fail")


def test_openai_compatible_urls_and_optional_auth_headers():
    from core.openai_compat import (
        bearer_headers, chat_completions_url, is_local_endpoint, model_discovery_urls,
    )
    assert chat_completions_url("http://localhost:11434/v1") == "http://localhost:11434/v1/chat/completions"
    assert chat_completions_url("https://api.example/v1/chat/completions/") == "https://api.example/v1/chat/completions"
    assert chat_completions_url("https://api.example/v1/responses") == "https://api.example/v1/chat/completions"
    assert bearer_headers("") == {}
    assert bearer_headers("secret") == {"Authorization": "Bearer secret"}
    assert is_local_endpoint("http://localhost:11434/v1")
    assert is_local_endpoint("http://127.0.0.1:8000/v1")
    assert not is_local_endpoint("https://api.example.com/v1")
    assert model_discovery_urls("http://localhost:11434/v1") == (
        "http://localhost:11434/v1/models", "http://localhost:11434/api/tags")


def test_behavior_defaults_include_safe_idle_interval(tmp_path):
    config = Config(tmp_path / "config.json")
    assert config.get("behavior", "click_action") == "switch_sprite"
    assert config.get("behavior", "idle_interval") == 30


def test_startup_command_uses_current_interpreter(monkeypatch, tmp_path):
    from core.startup import launch_command
    import sys
    command = launch_command(tmp_path / "main.py")
    assert sys.executable in command
    assert "main.py" in command


def test_screen_request_cleanup_resets_transient_state(tmp_path):
    manager = type("Manager", (), {})()
    manager._screen_mode = "observation"
    manager._screen_prompt = "prompt"
    manager._screen_request_active = True
    manager._ocr_path = tmp_path / "capture.png"
    manager._ocr_path.write_bytes(b"image")
    manager.config = Config(tmp_path / "config.json")
    assert PetManager._finish_screen_request(manager) is True
    assert not manager._ocr_path.exists()
    assert manager._screen_mode == "manual"
    assert manager._screen_prompt == ""
    assert manager._screen_request_active is False


def test_stale_observation_reply_is_ignored_after_role_change():
    manager = type("Manager", (), {})()
    manager._observation_epoch = 1
    manager._role_epoch = 2
    manager._dialog = type("Dialog", (), {"isVisible": lambda self: True})()
    manager._disconnect_observation_signals = lambda: None
    manager._save_chat_history = lambda: (_ for _ in ()).throw(AssertionError("stale reply saved"))
    manager._set_pet_state = lambda _state: (_ for _ in ()).throw(AssertionError("stale state changed"))
    manager._speak = lambda _text: (_ for _ in ()).throw(AssertionError("stale reply spoken"))
    PetManager._on_observation_reply(manager, "old role reply")
    assert manager._observation_epoch is None


def test_manual_screen_content_is_routed_through_character_llm(tmp_path):
    class Signal:
        def __init__(self): self.connected = []
        def connect(self, callback): self.connected.append(callback)
        def disconnect(self, callback): self.connected.remove(callback)
    class Llm:
        def __init__(self):
            self.response_finished = Signal()
            self.error_occurred = Signal()
            self.user_messages = []
            self.context = ""
            self.sent = False
        def is_busy(self): return False
        def add_user_message(self, text, persist=True): self.user_messages.append((text, persist))
        def set_turn_context(self, context): self.context = context
        def send(self, stream): self.sent = not stream
    class Dialog:
        def __init__(self): self.messages = []
        def display_text(self, text, role): self.messages.append((text, role))
    manager = type("Manager", (), {})()
    manager.config = Config(tmp_path / "config.json")
    manager._llm = Llm()
    manager._dialog = Dialog()
    manager._role_epoch = 3
    manager._needs_initial_setup = lambda: False
    manager._configure_llm = lambda: None
    manager._set_pet_state = lambda _state: None
    manager._on_screen_response = lambda _text: None
    manager._on_screen_response_error = lambda _error: None
    manager._screen_thinking_message = lambda: "Noir 看到了……让我想想该怎么说。"
    PetManager._respond_to_screen_content(manager, "A document editor is open.", "", "视觉理解")
    assert manager._llm.user_messages[0][1] is False
    assert "A document editor is open." in manager._llm.context
    assert manager._llm.sent
    assert manager._dialog.messages[-1][1] == "assistant"
    assert "A document editor is open." not in manager._dialog.messages[-1][0]
    assert "背景线索" in manager._llm.context
    assert "不是逐项描述" in manager._llm.context


def test_screen_observation_messages_use_current_character_name(tmp_path):
    manager = type("Manager", (), {})()
    manager.config = Config(tmp_path / "config.json")
    manager._char_data = {"noir": type("Character", (), {"name": "Noir"})()}
    assert PetManager._screen_observation_message(manager) == "Noir 正在悄悄观察一下……"
    assert PetManager._screen_thinking_message(manager) == "Noir 看到了……让我想想该怎么说。"


def test_cloud_vision_readiness_requires_upload_consent(tmp_path):
    from ui.settings.service_status import vision_connection_ready
    assert not vision_connection_ready("https://vision.example/v1", "vision-model", False)
    assert vision_connection_ready("https://vision.example/v1", "vision-model", True)
    assert vision_connection_ready("http://localhost:11434/v1", "llava", False)


def test_observation_requires_both_chat_and_vision_services(tmp_path):
    from ui.settings.service_status import observation_ready
    config = Config(tmp_path / "config.json")
    config.set("screen_capture", "auto_observe", True)
    config.set("vision", "enabled", True)
    config.set("vision", "base_url", "http://localhost:11434/v1")
    config.set("vision", "model", "llava")
    assert not observation_ready(config)
    config.set("llm", "base_url", "http://localhost:11434/v1")
    config.set("llm", "model", "qwen3")
    assert observation_ready(config)


def test_local_compatible_services_are_ready_without_api_keys(tmp_path):
    from ui.settings.service_status import asr_ready, llm_ready, tts_ready
    config = Config(tmp_path / "config.json")
    config.set("llm", "base_url", "http://localhost:11434/v1")
    config.set("llm", "model", "qwen3")
    config.set("tts", "enabled", True)
    config.set("tts", "provider", "gpt_sovits_remote")
    config.set("tts", "base_url", "http://127.0.0.1:8000/v1")
    config.set("tts", "remote_reference_audio", "/models/noir/reference.ogg")
    config.set("asr", "enabled", True)
    config.set("asr", "provider", "cloud")
    config.set("asr", "base_url", "http://localhost:8001/v1")
    config.set("asr", "model", "whisper")
    assert llm_ready(config)
    assert tts_ready(config)
    assert asr_ready(config)


def test_initial_setup_accepts_local_llm_without_key(tmp_path):
    manager = type("Manager", (), {})()
    manager.config = Config(tmp_path / "config.json")
    manager.config.set("llm", "base_url", "http://localhost:11434/v1")
    manager.config.set("llm", "model", "qwen3")
    assert not PetManager._needs_initial_setup(manager)
    manager.config.set("llm", "base_url", "https://api.example/v1")
    assert PetManager._needs_initial_setup(manager)


def test_settings_window_public_page_route(qapp, tmp_path):
    from ui.settings_window import SettingsWindow
    window = SettingsWindow(Config(tmp_path / "config.json"), ["noir"], "noir", tmp_path)
    window.open_page("vision")
    assert window._stack.currentWidget() is window._pages["vision"]


def test_settings_window_uses_static_starfield_shell(qapp, tmp_path):
    from ui.settings_components import ServiceStatusCard
    from ui.settings_window import SettingsWindow

    window = SettingsWindow(Config(tmp_path / "config.json"), ["noir"], "noir", tmp_path)
    assert window._starfield.objectName() == "settings_starfield"
    assert len(window._starfield._stars) >= 60
    assert len(window._starfield._constellations) >= 3
    assert window._starfield._meteor_cycle.interval() == 9000
    assert not window._starfield._meteor_timer.isActive()
    assert window._nav_frame.objectName() == "settings_navigation"
    assert window.findChild(type(window._starfield), "settings_starfield") is window._starfield
    card = ServiceStatusCard("服务", "说明")
    assert card.badge.objectName() == "service_status_badge"
    card.set_state(True)
    assert card.badge.text() == "已就绪"
    confirm = next(
        button for button in window.findChildren(QPushButton)
        if button.text() == "确定"
    )
    assert confirm.objectName() == "settings_confirm_button"


def test_settings_window_text_navigation_keeps_child_routing(qapp, tmp_path):
    from ui.settings_window import SettingsWindow

    window = SettingsWindow(Config(tmp_path / "config.json"), ["noir"], "noir", tmp_path)
    parent = window._tree.topLevelItem(1)
    child = parent.child(1)
    assert parent.icon(0).isNull()
    assert child.icon(0).isNull()
    window._tree.setCurrentItem(child)
    assert window._stack.currentWidget() is window._pages["character_sprites"]
    assert window._nav_frame.width() == 208
    assert window.width() >= 980


def test_settings_window_offers_live2d_when_the_model_is_present(qapp, tmp_path):
    from ui.settings_window import SettingsWindow

    model_dir = tmp_path / "characters" / "noir" / "sprites" / "live2d" / "NOIR"
    model_dir.mkdir(parents=True)
    (model_dir / "noir.model3.json").write_text("{}", encoding="utf-8")
    window = SettingsWindow(Config(tmp_path / "config.json"), ["noir"], "noir", tmp_path)
    window.open_page("character_sprites")
    assert window._renderer_combo.findData("static") >= 0
    assert window._renderer_combo.findData("live2d") >= 0
    window._renderer_combo.setCurrentIndex(window._renderer_combo.findData("live2d"))
    assert window._collect_settings()["window"]["renderer"] == "live2d"


def test_independent_settings_pages_build_without_window():
    from ui.settings.pages import make_about_page, make_character_parent_page
    assert make_about_page().layout() is not None
    assert make_character_parent_page().layout() is not None


def test_screen_and_vision_page_factories_expose_form_fields(qapp, tmp_path):
    from ui.settings.pages import make_screen_page, make_vision_page
    config = Config(tmp_path / "config.json")
    _, screen = make_screen_page(config, lambda _layout, _key, _text: None)
    _, vision = make_vision_page(config, lambda _layout, _key, _text: None)
    assert {"screen_hotkey", "screen_auto_observe", "screen_vision_max_dimension"}.issubset(screen)
    assert {"vision_url", "vision_allow_cloud"}.issubset(vision)


def test_voice_page_factories_switch_provider_rows(qapp, tmp_path):
    from ui.settings.pages import make_asr_page, make_tts_page
    from ui.settings_window import SettingsWindow
    config = Config(tmp_path / "config.json")
    _, tts, tts_rows = make_tts_page(config, lambda _layout, _key, _text: None)
    _, asr, asr_rows = make_asr_page(config, lambda _layout, _key, _text: None)
    assert {"tts_model", "tts_api_url"}.issubset(tts_rows)
    assert "tts_sync_text" not in tts
    assert "tts_translate" not in tts
    assert {"asr_model", "asr_api_url"}.issubset(asr_rows)
    window = SettingsWindow(config, ["noir"], "noir", tmp_path)
    window._tts_provider.setCurrentIndex(window._tts_provider.findData("gpt_sovits_remote"))
    window._asr_provider.setCurrentIndex(window._asr_provider.findData("cloud"))
    assert window._tts_rows["tts_model"].isHidden()
    assert not window._tts_rows["tts_api_url"].isHidden()
    assert window._asr_rows["asr_model"].isHidden()
    assert not window._asr_rows["asr_api_url"].isHidden()


def test_ai_page_factory_exposes_connection_and_format_controls(qapp, tmp_path):
    from ui.settings.pages import make_ai_page
    _, fields = make_ai_page(Config(tmp_path / "config.json"))
    assert {"ai_url", "ai_key", "ai_model", "ai_post", "ai_test_button", "ai_provider_preset"}.issubset(fields)


def test_provider_presets_recognize_known_and_custom_endpoints():
    from ui.settings.provider_presets import CHAT_PRESETS, preset_by_key, preset_key_for_url
    assert preset_key_for_url("http://localhost:11434/v1/", CHAT_PRESETS) == "ollama"
    assert preset_key_for_url("https://example.test/v1", CHAT_PRESETS) == "custom"
    assert preset_by_key("deepseek", CHAT_PRESETS).default_model == "deepseek-chat"


def test_settings_window_applies_chat_provider_preset(qapp, tmp_path):
    from ui.settings_window import SettingsWindow
    config = Config(tmp_path / "config.json")
    window = SettingsWindow(config, ["noir"], "noir", tmp_path)
    window._ai_provider_preset.setCurrentIndex(window._ai_provider_preset.findData("ollama"))
    assert window._ai_url.text() == "http://localhost:11434/v1"
    assert window._ai_model.text() == "qwen3:8b"


def test_settings_window_marks_local_chat_service_ready(qapp, tmp_path):
    from ui.settings_window import SettingsWindow
    config = Config(tmp_path / "config.json")
    window = SettingsWindow(config, ["noir"], "noir", tmp_path)
    window._ai_url.setText("http://localhost:11434/v1")
    window._ai_key.clear()
    window._ai_model.setText("qwen3")
    window._refresh_service_status_cards()
    assert window._ai_status_card.badge.text() == "已就绪"


def test_settings_window_tracks_unsaved_form_changes(qapp, tmp_path):
    from ui.settings_window import SettingsWindow
    window = SettingsWindow(Config(tmp_path / "config.json"), ["noir"], "noir", tmp_path)
    assert not window._has_unsaved_changes()
    window._ai_model.setText("changed-model")
    assert window._has_unsaved_changes()
    assert window._dirty_label.text() == "有未保存的更改"


def test_settings_window_only_accepts_after_successful_apply(qapp, tmp_path, monkeypatch):
    from ui.settings_window import SettingsWindow
    window = SettingsWindow(Config(tmp_path / "config.json"), ["noir"], "noir", tmp_path)
    monkeypatch.setattr(window, "_on_apply", lambda: False)
    window._on_ok()
    assert window.result() == 0


def test_stream_finish_replaces_unprocessed_display(qapp):
    from ui.dialog_window import DialogWindow
    window = DialogWindow("Test")
    window.start_stream()
    window.append_stream("visible<think>hidden</think>")
    window.finish_stream("visible")
    assert window._text_display.toPlainText() == "visible"


def test_stream_hides_stage_directions_before_the_reply_is_finished(qapp):
    from ui.dialog_window import DialogWindow
    window = DialogWindow("Test")
    window.start_stream()
    window.append_stream("（轻轻点头）")
    assert window._text_display.toPlainText() == ""
    window.append_stream("我明白了。")
    assert window._text_display.toPlainText() == "我明白了。"


def test_dialog_exposes_voice_and_screen_actions(qapp):
    from ui.dialog_window import DialogWindow
    window = DialogWindow("Test")
    events = []
    window.voice_pressed.connect(lambda: events.append("voice-start"))
    window.voice_released.connect(lambda: events.append("voice-stop"))
    window.screen_capture_requested.connect(lambda: events.append("screen"))
    assert window._voice_btn.isEnabled()
    window._voice_btn.pressed.emit()
    window._voice_btn.released.emit()
    window._screen_btn.click()
    assert events == ["voice-start", "voice-stop", "screen"]
    window.set_voice_available(False)
    assert not window._voice_btn.isEnabled()


def test_dialog_actions_show_recording_and_screen_busy_state(qapp):
    from ui.dialog_window import DialogWindow
    window = DialogWindow("Test")
    window.set_voice_recording(True)
    assert window._voice_btn.text() == "松开结束"
    window.set_voice_recording(False)
    assert window._voice_btn.text() == "按住说话"
    window.set_screen_busy(True)
    assert not window._screen_btn.isEnabled()
    assert window._screen_btn.text() == "识图中..."
    window.set_screen_busy(False)
    assert window._screen_btn.isEnabled()


def test_voice_recorder_cancel_discards_active_stream():
    from core.voice_input import PushToTalkRecorder
    class Stream:
        def __init__(self):
            self.stopped = self.closed = False
        def stop(self): self.stopped = True
        def close(self): self.closed = True
    recorder = PushToTalkRecorder()
    stream = Stream()
    recorder._stream = stream
    recorder.cancel()
    assert stream.stopped and stream.closed and not recorder.recording


def test_tray_observation_state_updates_without_signal(qapp):
    from ui.tray_icon import TrayIcon
    tray = TrayIcon("Test", observe_enabled=False)
    tray.set_observation_enabled(True)
    assert tray._observe_action.isChecked()


def test_vision_payload_downsizes_image_when_requested(tmp_path):
    pytest = __import__("pytest")
    Image = pytest.importorskip("PIL.Image")
    from core.vision_service import image_data_url_payload
    import base64
    from io import BytesIO
    path = tmp_path / "large.png"
    Image.new("RGB", (2400, 1200), "white").save(path)
    payload, mime = image_data_url_payload(path, 800)
    result = Image.open(BytesIO(base64.b64decode(payload)))
    assert mime == "image/jpeg"
    assert max(result.size) == 800
