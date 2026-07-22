"""Small Windows automation bridge for a locally running Cubism Editor.

Use only on a desktop session you control.  Coordinates passed to click/drag
are relative to the Cubism client area so a script does not depend on a fixed
screen resolution.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import time
import base64


user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Cubism is per-monitor DPI aware. Match its coordinate space before querying
# window bounds so screenshots, UI positions, and injected mouse coordinates
# all use the same physical pixels.
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except AttributeError:
    pass

SW_RESTORE = 9
VK_CONTROL = 0x11
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1
SRCCOPY = 0x00CC0020

# Both screenshots and injection use physical pixels after DPI awareness.
POINTER_SCALE = float(os.environ.get("CUBISM_POINTER_SCALE", "1.0"))
POINTER_OFFSET_X = int(os.environ.get("CUBISM_POINTER_OFFSET_X", "0"))
POINTER_OFFSET_Y = int(os.environ.get("CUBISM_POINTER_OFFSET_Y", "0"))


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
               ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
user32.FindWindowW.restype = wintypes.HWND
user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(RECT))
user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(RECT))
user32.ClientToScreen.argtypes = (wintypes.HWND, ctypes.POINTER(POINT))
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
user32.BringWindowToTop.argtypes = (wintypes.HWND,)
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.IsIconic.argtypes = (wintypes.HWND,)
user32.IsIconic.restype = wintypes.BOOL
user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
user32.mouse_event.argtypes = (
    wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t,
)
user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)


def cubism_window() -> int:
    """Return the window handle for the currently open Cubism Editor."""
    handle = user32.FindWindowW(None, "Live2D Cubism Editor 5.3.03    [ 试用版 剩余 42 天 ]  - noir")
    if handle:
        return handle

    # PowerShell can query the title without relying on optional Python packages.
    command = (
        "Get-Process java -ErrorAction SilentlyContinue | "
        "Where-Object {$_.MainWindowTitle -like '*Live2D Cubism Editor*'} | "
        "Select-Object -First 1 -ExpandProperty MainWindowHandle"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return int(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError("Cubism Editor window was not found.") from exc


def client_bounds(handle: int) -> tuple[int, int, int, int]:
    rect = RECT()
    if not user32.GetClientRect(handle, ctypes.byref(rect)):
        raise ctypes.WinError(ctypes.get_last_error())
    origin = POINT(0, 0)
    if not user32.ClientToScreen(handle, ctypes.byref(origin)):
        raise ctypes.WinError(ctypes.get_last_error())
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise RuntimeError(
            "Cubism is not available on this interactive desktop "
            f"(client area {width}x{height} at {origin.x},{origin.y}). "
            "Run this bridge from the same visible Windows desktop as Cubism."
        )
    return origin.x, origin.y, width, height


def focus(handle: int) -> None:
    # Restoring an already maximized window silently turns it into a normal
    # window. Only restore it when it is genuinely minimized.
    if user32.IsIconic(handle):
        user32.ShowWindow(handle, SW_RESTORE)
    if user32.GetForegroundWindow() != handle:
        foreground = user32.GetForegroundWindow()
        foreground_thread = user32.GetWindowThreadProcessId(foreground, None)
        current_thread = kernel32.GetCurrentThreadId()
        attached = bool(foreground_thread) and bool(
            user32.AttachThreadInput(current_thread, foreground_thread, True)
        )
        try:
            user32.ShowWindow(handle, SW_RESTORE if user32.IsIconic(handle) else 5)
            user32.BringWindowToTop(handle)
            user32.SetForegroundWindow(handle)
        finally:
            if attached:
                user32.AttachThreadInput(current_thread, foreground_thread, False)
        if user32.GetForegroundWindow() != handle:
            raise RuntimeError("Cubism could not be brought to the foreground; no input was sent.")
    time.sleep(0.25)


def point(handle: int, x: int, y: int) -> tuple[int, int]:
    left, top, width, height = client_bounds(handle)
    if not 0 <= x < width or not 0 <= y < height:
        raise ValueError(f"({x}, {y}) lies outside Cubism client area {width}x{height}.")
    return (
        left + round(x * POINTER_SCALE) + POINTER_OFFSET_X,
        top + round(y * POINTER_SCALE) + POINTER_OFFSET_Y,
    )


def click(handle: int, x: int, y: int) -> None:
    sx, sy = point(handle, x, y)
    focus(handle)
    user32.SetCursorPos(sx, sy)
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # left down
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # left up


def raw_click(handle: int, x: int, y: int) -> None:
    """Click a native Cubism chrome coordinate (menu bar/dialog controls)."""
    left, top, width, height = client_bounds(handle)
    if not 0 <= x < width or not 0 <= y < height:
        raise ValueError(f"({x}, {y}) lies outside Cubism client area {width}x{height}.")
    focus(handle)
    user32.SetCursorPos(left + x, top + y)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


def drag(handle: int, x1: int, y1: int, x2: int, y2: int, duration: float) -> None:
    start = point(handle, x1, y1)
    end = point(handle, x2, y2)
    focus(handle)
    user32.SetCursorPos(*start)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    steps = max(2, round(duration * 60))
    for step in range(1, steps + 1):
        ratio = step / steps
        user32.SetCursorPos(
            round(start[0] + (end[0] - start[0]) * ratio),
            round(start[1] + (end[1] - start[1]) * ratio),
        )
        time.sleep(duration / steps)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


def scroll(handle: int, x: int, y: int, clicks: int) -> None:
    """Scroll while the pointer is over a Cubism panel."""
    sx, sy = point(handle, x, y)
    focus(handle)
    user32.SetCursorPos(sx, sy)
    user32.mouse_event(0x0800, 0, 0, clicks * 120, 0)


def send_hotkey(keys: str) -> None:
    """Send a shortcut such as ctrl+s, ctrl+shift+s, or alt+f."""
    pieces = [item.strip().lower() for item in keys.split("+")]
    modifiers = {"ctrl": VK_CONTROL, "shift": 0x10, "alt": 0x12}
    named_keys = {"enter": 0x0D, "escape": 0x1B, "delete": 0x2E, "tab": 0x09}
    if not pieces or pieces[-1] in modifiers:
        raise ValueError("Shortcut must end with one key, for example ctrl+s.")
    key = named_keys.get(pieces[-1], ord(pieces[-1].upper()) if len(pieces[-1]) == 1 else None)
    if key is None:
        raise ValueError("Unsupported key name.")
    held = [modifiers[item] for item in pieces[:-1]]
    if any(item not in modifiers for item in pieces[:-1]):
        raise ValueError("Supported modifiers are ctrl, shift, and alt.")
    for code in held:
        user32.keybd_event(code, 0, 0, 0)
    user32.keybd_event(key, 0, 0, 0)
    user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)
    for code in reversed(held):
        user32.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)


def hotkey(handle: int, keys: str) -> None:
    focus(handle)
    send_hotkey(keys)


def paste(handle: int, x: int, y: int, value: str) -> None:
    """Replace a focused text field using the local Windows clipboard."""
    encoded = base64.b64encode(value.encode("utf-16-le")).decode("ascii")
    command = f"Set-Clipboard -Value ([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{encoded}')))"
    subprocess.run(["powershell", "-NoProfile", "-Command", command], check=True)
    click(handle, x, y)
    send_hotkey("ctrl+a")
    send_hotkey("ctrl+v")


def screenshot(handle: int, destination: Path) -> None:
    """Capture just the Cubism client region to a PNG through PowerShell."""
    left, top, width, height = client_bounds(handle)
    destination.parent.mkdir(parents=True, exist_ok=True)
    script = f"""
Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap {width}, {height}
$graphics = [System.Drawing.Graphics]::FromImage($bmp)
$graphics.CopyFromScreen({left}, {top}, 0, 0, $bmp.Size)
$bmp.Save('{destination}', [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose(); $bmp.Dispose()
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("inspect")
    actions.add_parser("focus")
    click_parser = actions.add_parser("click")
    click_parser.add_argument("x", type=int)
    click_parser.add_argument("y", type=int)
    raw_click_parser = actions.add_parser("raw-click")
    raw_click_parser.add_argument("x", type=int)
    raw_click_parser.add_argument("y", type=int)
    drag_parser = actions.add_parser("drag")
    drag_parser.add_argument("x1", type=int)
    drag_parser.add_argument("y1", type=int)
    drag_parser.add_argument("x2", type=int)
    drag_parser.add_argument("y2", type=int)
    drag_parser.add_argument("--duration", type=float, default=0.4)
    scroll_parser = actions.add_parser("scroll")
    scroll_parser.add_argument("x", type=int)
    scroll_parser.add_argument("y", type=int)
    scroll_parser.add_argument("clicks", type=int)
    key_parser = actions.add_parser("hotkey")
    key_parser.add_argument("keys")
    paste_parser = actions.add_parser("paste")
    paste_parser.add_argument("x", type=int)
    paste_parser.add_argument("y", type=int)
    paste_parser.add_argument("value")
    shot_parser = actions.add_parser("screenshot")
    shot_parser.add_argument("path", type=Path)
    args = parser.parse_args()

    handle = cubism_window()
    try:
        left, top, width, height = client_bounds(handle)
    except RuntimeError as exc:
        print(f"Cubism handle={handle}; unavailable: {exc}")
        if args.action == "inspect":
            return
        raise
    print(
        f"Cubism handle={handle}; client=({left}, {top}) {width}x{height}; "
        f"pointer_scale={POINTER_SCALE}; "
        f"pointer_offset=({POINTER_OFFSET_X}, {POINTER_OFFSET_Y})"
    )
    if args.action == "inspect":
        return
    if args.action == "focus":
        focus(handle)
    elif args.action == "click":
        click(handle, args.x, args.y)
    elif args.action == "raw_click":
        raw_click(handle, args.x, args.y)
    elif args.action == "drag":
        drag(handle, args.x1, args.y1, args.x2, args.y2, args.duration)
    elif args.action == "scroll":
        scroll(handle, args.x, args.y, args.clicks)
    elif args.action == "hotkey":
        hotkey(handle, args.keys)
    elif args.action == "paste":
        paste(handle, args.x, args.y, args.value)
    elif args.action == "screenshot":
        screenshot(handle, args.path)


if __name__ == "__main__":
    main()
