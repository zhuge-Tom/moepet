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
    events = []
    manager._save_chat_history = lambda: events.append("save-old")
    manager._load_knowledge_base = lambda: events.append("load-knowledge")
    manager._load_chat_history = lambda: events.append("load-new")

    PetManager._switch_character(manager, "new")

    assert manager.config.current_character == "new"
    assert manager._llm.cancelled and manager._llm.cleared
    assert events == ["save-old", "load-knowledge", "load-new"]


def test_config_has_multimodal_defaults(tmp_path):
    config = Config(tmp_path / "config.json")
    assert config.get("asr", "compute_type") == "int8"
    assert config.get("screen_capture", "keep_captures") is False
    assert config.get("screen_capture", "auto_observe") is False
    assert config.get("screen_capture", "observe_min_interval") == 300


def test_cloud_asr_endpoint_is_completed(tmp_path):
    from core.asr_service import ASRService
    service = ASRService()
    assert service.transcribe_cloud(tmp_path / "missing.wav", "", "", "whisper-1") is False


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
