"""Moepet - 萌系桌面宠物

基于 PySide6 的桌面宠物应用，支持多角色、
Galgame 风格对话框、立绘动画演出。
"""

import sys
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from core.config import Config
from core.signals import signals
from pet_manager import PetManager

BASE_DIR = Path(__file__).parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Moepet")

    if hasattr(Qt, "AA_UseSoftwareOpenGL"):
        app.setAttribute(Qt.AA_UseSoftwareOpenGL)

    config = Config(BASE_DIR / "config.json")
    manager = PetManager(BASE_DIR, config)

    # 退出信号
    signals.quit_requested.connect(app.quit)

    manager.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
