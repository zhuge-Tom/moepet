"""
Moepet - 萌系桌面宠物
基于 PySide6，支持多角色切换的桌面宠物
"""

import sys
import json
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from core.pet_manager import PetManager

BASE_DIR = Path(__file__).parent
CHARACTERS_DIR = BASE_DIR / "characters"


def load_config() -> dict:
    """加载全局配置"""
    config_path = BASE_DIR / "config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"current_character": "nuowa"}


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 允许透明窗口
    if hasattr(Qt, "AA_UseSoftwareOpenGL"):
        app.setAttribute(Qt.AA_UseSoftwareOpenGL)

    config = load_config()
    manager = PetManager(CHARACTERS_DIR, config)

    manager.show_current()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
