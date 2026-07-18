from pathlib import Path
import json

from core.character import CharacterLoader
from core.config import Config
from pet_manager import PetManager
from core.knowledge_base import KnowledgeBase


def test_character_config_keeps_its_own_prompt(tmp_path):
    char_dir = tmp_path / "pet"
    char_dir.mkdir(parents=True)
    (char_dir / "config.json").write_text(json.dumps({
        "name": "Pet",
        "character_prompt": {"system_prompt": "pet-only", "format_prompt": ""},
    }), encoding="utf-8")
    data = CharacterLoader(tmp_path).load("pet")
    assert data.character_prompt["system_prompt"] == "pet-only"


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


def test_remote_audio_services_require_a_key_without_starting_work(tmp_path):
    from core.asr_service import ASRService
    from core.tts_service import TTSService
    asr = ASRService()
    tts = TTSService()
    assert asr.transcribe_cloud(tmp_path / "missing.wav", "https://api.example/v1", "", "whisper-1") is False
    assert tts.synthesize_cloud("hello", "https://api.example/v1", "", "tts-1", "alloy", tmp_path / "out.wav") is False


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
    config.set("tts", "provider", "cloud")
    config.set("tts", "base_url", "https://example.test")
    config.set("tts", "model", "tts-1")
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


def test_cloud_vision_readiness_requires_upload_consent(tmp_path):
    from ui.settings.service_status import vision_connection_ready
    assert not vision_connection_ready("https://vision.example/v1", "vision-model", False)
    assert vision_connection_ready("https://vision.example/v1", "vision-model", True)
    assert vision_connection_ready("http://localhost:11434/v1", "llava", False)


def test_local_compatible_services_are_ready_without_api_keys(tmp_path):
    from ui.settings.service_status import asr_ready, llm_ready, tts_ready
    config = Config(tmp_path / "config.json")
    config.set("llm", "base_url", "http://localhost:11434/v1")
    config.set("llm", "model", "qwen3")
    config.set("tts", "enabled", True)
    config.set("tts", "provider", "cloud")
    config.set("tts", "base_url", "http://127.0.0.1:8000/v1")
    config.set("tts", "model", "tts")
    config.set("tts", "voice", "alloy")
    config.set("asr", "enabled", True)
    config.set("asr", "provider", "cloud")
    config.set("asr", "base_url", "http://localhost:8001/v1")
    config.set("asr", "model", "whisper")
    assert llm_ready(config)
    assert tts_ready(config)
    assert asr_ready(config)


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
    assert {"asr_model", "asr_api_url"}.issubset(asr_rows)
    window = SettingsWindow(config, ["noir"], "noir", tmp_path)
    window._tts_provider.setCurrentIndex(window._tts_provider.findData("cloud"))
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
