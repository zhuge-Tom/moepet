"""Moepet - 萌系桌面宠物

基于 PySide6 的桌面宠物应用，支持多角色、
Galgame 风格对话框、立绘动画演出。
"""

import os
import sys
import ctypes
import logging
import importlib.util
import site
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from core.config import Config
from core.signals import signals
from pet_manager import PetManager

BASE_DIR = Path(__file__).parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def _ensure_live2d_runtime() -> None:
    """Restart with the project venv when the selected Python lacks Live2D."""
    if importlib.util.find_spec("live2d") is not None:
        return

    project_site_packages = BASE_DIR / ".venv" / "Lib" / "site-packages"
    if project_site_packages.is_dir():
        site.addsitedir(str(project_site_packages))
        importlib.invalidate_caches()
        if importlib.util.find_spec("live2d") is not None:
            return

    venv_python = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    try:
        already_using_venv = Path(sys.executable).resolve() == venv_python.resolve()
    except OSError:
        already_using_venv = False
    if venv_python.is_file() and not already_using_venv:
        os.execv(
            str(venv_python),
            [str(venv_python), str(BASE_DIR / "main.py"), *sys.argv[1:]],
        )
        return

    raise RuntimeError(
        "Live2D 运行时未安装。请执行："
        r".\.venv\Scripts\python.exe -m pip install live2d-py==0.7.0.4"
    )


def _configure_network_no_proxy() -> None:
    """让 Qt 和 Python urllib 完全不走代理，避免被 SpeedCat 7892 劫持。

    SpeedCat DLL 注入会导致 SSL 崩溃，moepet 的 API 请求（DeepSeek）
    可以直连，不需要经过代理。
    """
    # 1) Qt 网络栈 — QNetworkAccessManager 默认读系统代理
    from PySide6.QtNetwork import QNetworkProxy
    QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.NoProxy))

    # 2) Python urllib — vision/asr 等模块使用
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(var, None)
    os.environ["NO_PROXY"] = "*"


def main():
    _ensure_live2d_runtime()
    _configure_network_no_proxy()
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("zhuge-Tom.Moepet")
        except (AttributeError, OSError):
            pass
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Moepet")
    icon_path = BASE_DIR / "assets" / "moepet.ico"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Live2D uses a QOpenGLWidget. Software OpenGL remains an opt-in fallback
    # for machines that cannot create a hardware context.
    if os.environ.get("MOEPET_SOFTWARE_OPENGL") == "1" and hasattr(Qt, "AA_UseSoftwareOpenGL"):
        app.setAttribute(Qt.AA_UseSoftwareOpenGL)

    config = Config(BASE_DIR / "config.json")
    manager = PetManager(BASE_DIR, config)

    # 退出信号
    signals.quit_requested.connect(app.quit)

    manager.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
