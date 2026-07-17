from pathlib import Path
import json

from core.character import CharacterLoader
from core.config import Config
from pet_manager import PetManager


def test_config_has_multimodal_defaults(tmp_path):
    config = Config(tmp_path / "config.json")
    assert config.get("asr", "compute_type") == "int8"
    assert config.get("screen_capture", "keep_captures") is False


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
