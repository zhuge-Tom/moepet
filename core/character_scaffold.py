"""Safe, isolated character-directory scaffolding."""

from __future__ import annotations

import json
import re
from pathlib import Path


CHARACTER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def find_live2d_model(character_dir: Path) -> Path | None:
    """Return this character's own model without relying on Noir's layout."""
    root = Path(character_dir) / "sprites" / "live2d"
    return next(iter(sorted(root.rglob("*.model3.json"))), None) if root.exists() else None


def create_character_scaffold(characters_dir: Path, character_id: str,
                              display_name: str, renderer: str = "live2d") -> Path:
    character_id = character_id.strip()
    display_name = display_name.strip()
    if not CHARACTER_ID_RE.fullmatch(character_id):
        raise ValueError("角色目录名只能包含英文字母、数字、下划线和连字符（最多 40 位）。")
    if not display_name:
        raise ValueError("角色显示名称不能为空。")
    if renderer not in {"static", "live2d"}:
        raise ValueError("未知的立绘类型。")

    root = Path(characters_dir)
    target = root / character_id
    if target.exists():
        raise FileExistsError(f"角色目录已存在：{character_id}")

    # Resolve before writing so a future validation change cannot escape characters/.
    if target.resolve().parent != root.resolve():
        raise ValueError("角色目录必须位于 characters 文件夹内。")

    sprites = target / "sprites"
    (sprites / "live2d").mkdir(parents=True)
    (target / "knowledge" / "sources").mkdir(parents=True)
    (target / "memory" / "summaries").mkdir(parents=True)
    for kind in ("diary", "weekly", "monthly", "quarterly", "yearly"):
        (target / "memory" / "archives" / kind).mkdir(parents=True)

    config = {
        "name": display_name,
        "name_en": character_id,
        "source": "",
        "scale": 0.6,
        "preferred_renderer": renderer,
        "sprites": {"idle": "idle.png"},
        "blinks": {},
        "interactions": {"head_touch": []},
        "voice": {},
        "character_prompt": {
            "system_prompt": f"你正在扮演 {display_name}。请使用自然、真诚、符合角色设定的中文回答。",
            "format_prompt": "",
        },
    }
    (target / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    (target / "animations.json").write_text("{}\n", encoding="utf-8")
    guide = f"""# {display_name} 角色配置指南

此目录只属于 `{character_id}`，聊天历史、资料库和记忆不会与其他角色共用。

## 配置角色

编辑 `config.json`：

- `name`：界面显示名称。
- `character_prompt.system_prompt`：角色身份、性格、语言风格与边界。
- `scale`：默认立绘比例。

## 放入立绘

### Live2D

将完整模型目录放入 `sprites/live2d/`。Moepet 会递归寻找该角色自己的 `.model3.json`。

### 静态 PNG（可选）

如果不使用 Live2D，可将透明 PNG 放入 `sprites/`，至少提供 `idle.png`；然后在 `config.json` 的 `sprites` 中配置情绪映射。

## 可选资料与语音

- 世界观和角色资料可通过设置页导入 `knowledge/sources/`。
- 语音参考文件放入角色自己的 `voice/`，不要与其他角色共用路径。

## 启用

完成素材配置后重新启动 Moepet，新角色会出现在“通用设置 → 角色选择”中。
"""
    (target / "角色配置指南.md").write_text(guide, encoding="utf-8")
    return target
