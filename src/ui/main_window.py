"""The single window: a list of connected Apple devices, one button each."""

from __future__ import annotations

import itertools
import logging
import subprocess
from collections.abc import Awaitable, Callable
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .. import update
from ..bridge import AsyncBridge
from ..device import POLL_MS, Device
from ..device import scan as usb_scan
from ..webdav import BASE_PORT, DeviceWebdav
from .style import build_stylesheet, system_palette

logger = logging.getLogger(__name__)

# Segoe Fluent Icons ships with Windows 11: tablet, phone, devices.
ICON_FONT = "Segoe Fluent Icons"
ICON_TABLET, ICON_PHONE, ICON_DEVICES = "", "", ""


def _label(text: str, name: str, icon_size: int = 0, center: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    if icon_size:
        # Set in code, not QSS: a stylesheet font-family overrides setFont, and
        # Qt then draws the private-use codepoint as a colour emoji.
        label.setFont(QFont(ICON_FONT, icon_size))
    if icon_size or center:
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def _empty_card() -> QFrame:
    box = QFrame()
    box.setObjectName("emptyCard")
    col = QVBoxLayout(box)
    col.setContentsMargins(20, 30, 20, 30)
    col.setSpacing(6)
    col.addWidget(_label(ICON_DEVICES, "emptyIcon", icon_size=26))
    col.addWidget(_label("No devices connected", "emptyTitle", center=True))
    col.addWidget(_label("Plug in an iPhone or iPad, unlock it, and tap Trust", "emptyHint", center=True))
    return box


class DeviceRow(QFrame):
    def __init__(self, device: Device, url: str) -> None:
        super().__init__()
        self.setObjectName("card")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(12)

        icon = _label(ICON_TABLET if device.is_tablet else ICON_PHONE, "deviceIcon", icon_size=20)
        icon.setFixedWidth(32)
        row.addWidget(icon)

        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(_label(device.name, "deviceName"))
        text.addWidget(_label(device.subtitle, "deviceMeta"))
        row.addLayout(text, 1)

        self.open_btn = QPushButton("Open in File Explorer")
        self.open_btn.setObjectName("primary")
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.setToolTip(url)  # discoverable, and pasteable into Explorer's address bar
        self.open_btn.setEnabled(bool(url))
        row.addWidget(self.open_btn)


class MainWindow(QMainWindow):
    # (handler, future) pairs, emitted from the asyncio thread; Qt queues the
    # signal onto the GUI thread, which is what makes updating widgets safe.
    finished = Signal(object)

    def __init__(
        self,
        bridge: AsyncBridge,
        scan: Callable[[], Awaitable[list[Device]]] = usb_scan,
        session_factory: Callable[[str], Any] | None = None,
    ) -> None:
        super().__init__()
        self.bridge = bridge
        # Both injectable, so simulated devices can drive the window without
        # hardware - see tools/fake_devices.py. session_factory maps a UDID to
        # anything with AfcSession's surface; None means the real one.
        self._scan = scan
        self._session_factory = session_factory
        self._servers: dict[str, DeviceWebdav] = {}
        self._shown: dict[str, Device] = {}

        self.setWindowTitle("Hudzen")
        self.resize(560, 420)
        self.setMinimumSize(460, 300)
        self.setStyleSheet(build_stylesheet(system_palette()))

        central = QWidget()
        central.setObjectName("root")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(14)
        header = QVBoxLayout()
        header.setSpacing(2)
        header.addWidget(_label("Apple devices", "title"))
        self.status = _label("Looking for devices…", "subtitle")
        header.addWidget(self.status)
        outer.addLayout(header)

        self.update_bar = QFrame()
        self.update_bar.setObjectName("updateBar")
        self.update_bar.hide()
        bar = QHBoxLayout(self.update_bar)
        bar.setContentsMargins(14, 8, 14, 8)
        self.update_label = _label("", "deviceName")
        bar.addWidget(self.update_label, 1)
        self.update_btn = QPushButton("Install update")
        bar.addWidget(self.update_btn)
        outer.addWidget(self.update_bar)

        host = QWidget()
        host.setObjectName("listHost")
        self.list_layout = QVBoxLayout(host)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(host)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll, 1)
        self.setCentralWidget(central)
        self._render([])

        self.finished.connect(lambda pair: pair[0](pair[1]))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(POLL_MS)
        self._poll()
        self._call(update.check(), self._on_update_check)

    def _call(self, coro, handler) -> None:
        """Run a coroutine on the bridge and hand its future to handler on the GUI thread."""
        self.bridge.submit(coro).add_done_callback(lambda f: self.finished.emit((handler, f)))

    # -- devices ----------------------------------------------------------

    def _poll(self) -> None:
        self._call(self._scan(), self._on_scan)

    def _on_scan(self, future) -> None:
        try:
            devices: list[Device] = future.result()
        except Exception as exc:
            logger.debug("device scan failed", exc_info=exc)
            self.status.setText("Could not reach the Apple Devices service.")
            return
        current = {d.udid: d for d in devices}
        for udid in set(self._servers) - set(current):
            self._servers.pop(udid).stop()
        for udid in set(current) - set(self._servers):
            self._start_server(udid)
        if current != self._shown:  # rebuild only on change, so the 2s poll does not flicker
            self._shown = current
            self._render(devices)
        n = len(devices)
        self.status.setText(f"{n} device{'s' * (n != 1)} ready" if n else "Nothing connected")

    def _start_server(self, udid: str) -> None:
        used = {s.port for s in self._servers.values()}
        port = next(p for p in itertools.count(BASE_PORT) if p not in used)
        session = self._session_factory(udid) if self._session_factory else None
        server = DeviceWebdav(self.bridge, udid, port, session=session)
        try:
            server.start()
        except Exception:
            logger.warning("could not start WebDAV for %s", udid, exc_info=True)
            return
        self._servers[udid] = server
        logger.info("serving %s at %s", udid, server.url)

    def _render(self, devices: list[Device]) -> None:
        while self.list_layout.count() > 1:  # keep the trailing stretch
            self.list_layout.takeAt(0).widget().deleteLater()
        if not devices:
            self.list_layout.insertWidget(0, _empty_card())
        for i, device in enumerate(devices):
            server = self._servers.get(device.udid)
            row = DeviceRow(device, server.url if server else "")
            row.open_btn.clicked.connect(lambda _=False, u=row.open_btn.toolTip(): self._open(u))
            self.list_layout.insertWidget(i, row)

    def _open(self, url: str) -> None:
        # explorer.exe by name, so a UNC path always opens in Explorer, not whatever else Windows
        # might associate with it.
        subprocess.Popen(["explorer.exe", url])

    # -- updates ----------------------------------------------------------

    def _on_update_check(self, future) -> None:
        try:
            found = future.result()
        except Exception:  # offline, or no release yet: nothing to show
            logger.debug("update check failed", exc_info=True)
            return
        if found:
            version, url = found
            self.update_label.setText(f"Hudzen {version} is available")
            self.update_btn.clicked.connect(lambda: self._install_update(url))
            self.update_bar.show()

    def _install_update(self, url: str) -> None:
        self.update_btn.setEnabled(False)
        self.update_label.setText("Downloading…")
        self._call(update.install(url), self._on_update_installed)

    def _on_update_installed(self, future) -> None:
        try:
            future.result()
        except Exception:
            logger.warning("update download failed", exc_info=True)
            self.update_label.setText("Download failed; try again later")
            self.update_btn.setEnabled(True)
            return
        self.close()  # the installer is running; it relaunches Hudzen when done

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._timer.stop()
        for server in self._servers.values():
            server.stop()
        self._servers.clear()
        super().closeEvent(event)
