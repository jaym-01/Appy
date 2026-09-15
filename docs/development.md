# Development

## Setup

Python 3.11+, on Windows.

```bash
git clone https://github.com/jaym-01/Hudzen.git
cd Hudzen
pip install -r requirements.txt
python run.py
```

The Apple Devices app (or iTunes) must be installed for a real device to show
up. Everything else works without one.

## Layout

```
run.py              launch from source
src/                the app  (see docs/how-it-works.md for what each file does)
src/ui/             the window and its Windows 11 styling
tests/              unit tests and a simulated device
tools/build_exe.py  PyInstaller + Inno Setup
tools/demo_server.py  serve a fake device to Explorer
tools/fake_devices.py  the window with five fake devices
installer/hudzen.iss  Inno Setup script
.github/workflows/  CI: test, build, release
```

## Tests

```bash
python -m unittest discover -s tests -t .
```

No hardware needed. `tests/fake_device.py` stands in for a real device:
`FakeAfcSession` has the same surface as `AfcSession` but reads a local
directory laid out like an iPad's media folder, and `FakeDevice` wraps one in
a name, model and generated photos, so it can be served or shown like the real
thing. The WebDAV layer is exercised end to end over a real socket with the
same HTTP methods Explorer uses — only the device underneath is simulated.

The fake counts its own operations, which is how the cache is tested: a second
listing of the same folder must not reach the device at all.

To test against a real device, plug one in and run the app.

## Demo server

```bash
python tools/demo_server.py
```

Generates a folder of real JPEGs, serves it through the app's actual WebDAV
stack on port 2200, and opens Explorer on it. Use it to check Explorer
behaviour — thumbnails, preview pane, navigation — without a device attached.
Ctrl-C stops the server and deletes the folder.

## Fake devices in the window

```bash
python tools/fake_devices.py
```

Opens the real window with five simulated iPhones and iPads, each backed by
its own folder of JPEGs and its own WebDAV server, so every **Open in File
Explorer** button works. For screenshots, or for working on the window without
a device. `python tools/fake_devices.py 2` shows only the first two; the list
of names and models is `FLEET` at the top of the script. Closing the window
cleans up.

`MainWindow` takes `scan=` and `session_factory=` for this, mirroring
`DeviceWebdav(session=)`: the window never knows the devices are fake.

## Icon

`app.py` sets an explicit AppUserModelID. Without one a Python process
inherits the interpreter's, and the taskbar shows the Python icon.

## Conventions

- Comments explain *why*, not what. Most non-obvious decisions are documented
  next to the code that makes them.
- `pymobiledevice3` is imported inside functions, never at module top level —
  see [Lifecycle](how-it-works.md#lifecycle).
- Nothing in `webdav.py` implements a write method. Keep it that way.

## Git Bash

`pymobiledevice3` CLI commands with `/` paths fail under Git Bash because MSYS
rewrites them. Use PowerShell, or prefix with `MSYS_NO_PATHCONV=1`.
