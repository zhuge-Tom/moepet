"""Small threaded service helpers used by optional local AI integrations."""
import threading
from PySide6.QtCore import QObject, Signal


class BackgroundService(QObject):
    completed = Signal(object)
    failed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False

    def run(self, fn):
        if self._busy:
            return False
        self._busy = True
        self.busy_changed.emit(True)
        def task():
            try:
                result = fn()
            except Exception as exc:
                self.failed.emit(str(exc))
            else:
                self.completed.emit(result)
            finally:
                self._busy = False
                self.busy_changed.emit(False)
        threading.Thread(target=task, daemon=True).start()
        return True
