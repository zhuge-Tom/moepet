"""Optional global shortcut registration with a safe no-op fallback."""
from PySide6.QtCore import QObject, Signal


class HotkeyService(QObject):
    triggered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._handle = None
        self._press_handle = None
        self._release_handle = None

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

    def close(self):
        """Release every hook owned by this service before application exit."""
        self.unregister()
        self.unregister_push_to_talk()

    def register_push_to_talk(self, shortcut: str, on_press, on_release) -> bool:
        """Register a single-key or modifier shortcut for press/release capture."""
        self.unregister_push_to_talk()
        try:
            import keyboard
            self._press_handle = keyboard.add_hotkey(shortcut, on_press, suppress=False, trigger_on_release=False)
            # keyboard hotkeys do not expose a matching release event. The final
            # key is the practical push-to-talk release trigger.
            key = shortcut.lower().split("+")[-1].strip()
            self._release_handle = keyboard.on_release_key(key, lambda _event: on_release())
            return True
        except Exception:
            self.unregister_push_to_talk()
            return False

    def unregister_push_to_talk(self):
        try:
            import keyboard
            if self._press_handle is not None:
                keyboard.remove_hotkey(self._press_handle)
            if self._release_handle is not None:
                keyboard.unhook(self._release_handle)
        except Exception:
            pass
        self._press_handle = None
        self._release_handle = None
