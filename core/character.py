"""角色数据加载

每个角色一个目录，包含 config.json 和 sprites/ 文件夹。
支持多立绘映射、动画配置。
"""

import json
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class SpriteInfo:
    """单张立绘信息"""
    name: str
    path: Path


@dataclass
class AnimConfig:
    """立绘演出配置"""
    sprite_name: str
    animation: str = ""     # bounce / shake / enlarge / shrink / tremble
    particle: str = ""      # 粒子特效 gif 路径
    frames: list[str] = field(default_factory=list)
    frame_ms: int = 160
    loop: bool = True
    priority: int = 0


@dataclass
class CharacterData:
    """角色完整数据"""
    name: str
    name_en: str
    source: str = ""
    scale: float = 0.5
    sprites: list[SpriteInfo] = field(default_factory=list)
    default_sprite: str = ""
    sprite_map: dict[str, str] = field(default_factory=dict)
    animations: dict[str, AnimConfig] = field(default_factory=dict)
    voice: dict = field(default_factory=dict)
    character_prompt: dict = field(default_factory=dict)
    base_dir: Path = field(default_factory=Path)

    @property
    def sprite_dir(self) -> Path:
        return self.base_dir / "sprites"


class CharacterLoader:
    """扫描并加载角色数据"""

    def __init__(self, characters_dir: Path):
        self.characters_dir = characters_dir

    def list_names(self) -> list[str]:
        """列出所有可用角色名"""
        if not self.characters_dir.exists():
            return []
        names = []
        for d in sorted(self.characters_dir.iterdir()):
            if d.is_dir() and (d / "config.json").exists():
                names.append(d.name)
        return names

    def load(self, name: str) -> CharacterData | None:
        """加载指定角色的完整数据"""
        char_dir = self.characters_dir / name
        config_path = char_dir / "config.json"

        if not config_path.exists():
            return None

        try:
            # PowerShell and some editors emit UTF-8 BOM; accept both forms.
            with open(config_path, "r", encoding="utf-8-sig") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        char = CharacterData(
            name=raw.get("name", name),
            name_en=raw.get("name_en", name),
            source=raw.get("source", ""),
            scale=raw.get("scale", 0.5),
            default_sprite=raw.get("default_sprite", ""),
            sprite_map=raw.get("sprites", {}),
            voice=raw.get("voice", {}),
            character_prompt=raw.get("character_prompt", {}),
            base_dir=char_dir,
        )

        # 扫描实际图片文件
        sprites_dir = char_dir / "sprites"
        if sprites_dir.exists():
            for img in sorted(sprites_dir.glob("*.png")):
                char.sprites.append(SpriteInfo(name=img.stem, path=img))

        # 加载动画配置（可选）
        anim_path = char_dir / "animations.json"
        if anim_path.exists():
            try:
                with open(anim_path, "r", encoding="utf-8") as f:
                    anim_raw = json.load(f)
                for key, cfg in anim_raw.items():
                    cfg = cfg if isinstance(cfg, dict) else {}
                    char.animations[key] = AnimConfig(
                        sprite_name=key,
                        animation=cfg.get("animation", ""),
                        particle=cfg.get("particle", ""),
                        frames=cfg.get("frames", []),
                        frame_ms=max(30, int(cfg.get("frame_ms", 160))),
                        loop=bool(cfg.get("loop", True)),
                        priority=int(cfg.get("priority", 0)),
                    )
            except (json.JSONDecodeError, OSError):
                pass

        return char
