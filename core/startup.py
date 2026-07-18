"""Windows login-startup integration kept outside UI and pet lifecycle code."""

import os
import sys
from pathlib import Path


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Moepet"


def _quote(path: str) -> str:
    return f'"{path}"'


def launch_command(entrypoint: Path) -> str:
    """Build the current installation's startup command without a shell."""
    if getattr(sys, "frozen", False):
        return _quote(sys.executable)
    return f"{_quote(sys.executable)} {_quote(str(entrypoint))}"


def set_enabled(enabled: bool, entrypoint: Path) -> tuple[bool, str]:
    """Enable or remove per-user login startup on Windows.

    The app remains usable on other platforms; the caller receives an explicit
    result instead of silently persisting a setting that cannot take effect.
    """
    if os.name != "nt":
        return False, "开机自启目前仅支持 Windows"
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, launch_command(entrypoint))
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
    except OSError as exc:
        return False, f"无法更新开机自启：{exc}"
    return True, ""
