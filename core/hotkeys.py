"""Optional global shortcut registration with a safe no-op fallback."""
from PySide6.QtCore import QObject, Signal


class HotkeyService(QObject):
    triggered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._handle = None

    def register(self, shortcut: str) -> bool:
        self.unregister()
        try:
            import keyboard
            self._handle = keyboard.add_hotkey(shortcut, self.triggered.emit)
            return True
        except Exception:
            return False

    def unregister(self):
        if self._handle is not None:
            try:
                import keyboard
                keyboard.remove_hotkey(self._handle)
            except Exception:
                pass
            self._handle = None
