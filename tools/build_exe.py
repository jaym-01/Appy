"""Build Hudzen into a single .exe, then wrap it in an installer:

    python tools/build_exe.py

Produces dist/Hudzen.exe (PyInstaller) and dist/HudzenSetup.exe (Inno Setup, if
ISCC is installed: `winget install JRSoftware.InnoSetup`, or set ISCC to its
path). The target machine still needs the Apple Devices app, which supplies
the USB driver and the usbmux service.

    --console   keep a console window, for diagnosing a build that won't start
    --clean     discard PyInstaller's cache first
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src import __version__  # noqa: E402

ICON = ROOT / "assets" / "icon.ico"
ISCC = Path(os.environ.get("ISCC", r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"))

# pymobiledevice3 drags in tooling the AFC path never touches, and Qt ships far
# more than one window needs. xonsh and pygnuutils are deliberately absent:
# services/afc.py imports both at module level, so excluding them breaks the
# one import we depend on.
EXCLUDES = """IPython av ipsw_parser developer_disk_image pykdebugparser asgiwebdav fastapi
uvicorn starlette matplotlib tkinter pytest PyQt5 PyQt6 PySide2 numpy""".split() + [
    "PySide6." + m for m in """QtWebEngineCore QtWebEngineWidgets QtWebEngineQuick QtQuick
QtQuick3D QtQml QtMultimedia QtMultimediaWidgets QtCharts QtDataVisualization Qt3DCore
Qt3DRender QtBluetooth QtNfc QtPositioning QtSerialPort QtSql QtTest QtDesigner QtHelp
QtNetworkAuth QtRemoteObjects QtScxml QtSensors QtSpatialAudio QtTextToSpeech QtWebChannel
QtWebSockets QtPdf QtPdfWidgets""".split()
]

# xonsh resolves much of itself at runtime, so static analysis misses these.
# wsgidav/cheroot need nothing here: every component our config selects
# (SimpleDomainController, Cors, WsgiDavDirBrowser, ...) is a plain top-level
# import in the module that uses it, so PyInstaller's analysis already finds it.
HIDDEN = """xonsh.main xonsh.cli_utils xonsh.tools xonsh.procs xonsh.procs.jobs
xonsh.parsers xonsh.parsers.v310 xonsh.execer pygnuutils.cli.ls
pymobiledevice3.services.afc pymobiledevice3.lockdown pymobiledevice3.usbmux""".split()


def main() -> int:
    flags = sys.argv[1:]
    cmd = [
        sys.executable, "-m", "PyInstaller", "--onefile", "--noconfirm", "--log-level", "WARN",
        "--name", "Hudzen", "--icon", str(ICON),
        "--add-data", f"{ICON}{os.pathsep}assets",  # app.py finds it via sys._MEIPASS
        "--console" if "--console" in flags else "--windowed",
    ]
    if "--clean" in flags:
        cmd.append("--clean")
    for module in EXCLUDES:
        cmd += ["--exclude-module", module]
    for module in HIDDEN:
        cmd += ["--hidden-import", module]
    cmd.append(str(ROOT / "run.py"))

    print(f"[1/2] PyInstaller, Hudzen {__version__}; this takes a few minutes")
    code = subprocess.run(cmd, cwd=ROOT).returncode
    if code:
        return code
    exe = ROOT / "dist" / "Hudzen.exe"
    print(f"      {exe} ({exe.stat().st_size / 2**20:.1f} MB)")

    if not ISCC.is_file():
        print(f"[2/2] skipped: Inno Setup not found at {ISCC}")
        return 0
    print("[2/2] Inno Setup")
    code = subprocess.run([str(ISCC), "/Q", f"/DAppVersion={__version__}", str(ROOT / "installer" / "hudzen.iss")], cwd=ROOT).returncode
    if code == 0:
        setup = ROOT / "dist" / "HudzenSetup.exe"
        print(f"      {setup} ({setup.stat().st_size / 2**20:.1f} MB)")
    return code


if __name__ == "__main__":
    sys.exit(main())
