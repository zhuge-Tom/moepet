"""
Moepet - 萌系桌面宠物
基于 PySide6，支持多角色切换的桌面宠物
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from core.config import Config
from core.pet_manager import PetManager

BASE_DIR = Path(__file__).parent
CHARACTERS_DIR = BASE_DIR / "characters"


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if hasattr(Qt, "AA_UseSoftwareOpenGL"):
        app.setAttribute(Qt.AA_UseSoftwareOpenGL)

    config = Config(BASE_DIR / "config.json")
    manager = PetManager(CHARACTERS_DIR, config)

    manager.show_current()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
