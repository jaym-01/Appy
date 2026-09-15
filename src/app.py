"""Entry point."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .bridge import AsyncBridge
from .ui.main_window import MainWindow


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("pymobiledevice3").setLevel(logging.WARNING)  # chatty at INFO

    app = QApplication(sys.argv)
    app.setApplicationName("Appy")
    if sys.platform == "win32":
        # Windows groups taskbar buttons by AppUserModelID. Without an explicit
        # one a Python process inherits the interpreter's and shows its icon.
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Appy.Desktop")
    # assets/ sits beside src/ from source, and in sys._MEIPASS from a PyInstaller bundle.
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    app.setWindowIcon(QIcon(str(root / "assets" / "icon.ico")))

    bridge = AsyncBridge()
    window = MainWindow(bridge)
    window.show()
    try:
        return app.exec()
    finally:
        bridge.shutdown()
