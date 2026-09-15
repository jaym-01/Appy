# Building and releasing

## Build the installer locally

```bash
pip install pyinstaller
python tools/build_exe.py
```

Produces:

- `dist/Appy.exe` — one file, no Python needed on the target machine
- `dist/AppySetup.exe` — if [Inno Setup](https://jrsoftware.org/isinfo.php) is
  installed (`winget install JRSoftware.InnoSetup`, or set `ISCC` to its
  path). Skipped with a message otherwise.

Flags:

| Flag | Effect |
|---|---|
| `--clean` | Discard PyInstaller's cache first |
| `--console` | Keep a console window, for diagnosing a build that won't start |

The installer is per-user: no admin prompt, into
`%LocalAppData%\Programs\Appy`. The target machine still needs the Apple
Devices app for the USB driver and `usbmuxd`.

### What gets stripped

`pymobiledevice3` drags in firmware parsing, packet capture, a web server, and
PyAV, none of which the AFC path touches. `tools/build_exe.py` excludes them,
plus the Qt modules one window does not need.

**`xonsh` and `pygnuutils` must stay in.** `pymobiledevice3/services/afc.py`
imports both at module level; excluding them breaks the one import the app
depends on.

## CI

`.github/workflows/build.yml` runs on every push and pull request:

1. install dependencies
2. run the tests
3. build the installer

On a push to `master` it also publishes a GitHub Release with the installer
attached, unless one already exists for the current version. Other runs build
the installer only to prove the build works; nothing is kept from them.

## Releasing

1. Set `__version__` in `src/__init__.py`.
2. Commit and push to `master`.

CI tags the commit `v<version>`, builds the installer, and publishes a release
with generated notes and `AppySetup.exe` attached. Nothing to tag by hand.

A push that does not bump the version builds and tests as usual but does not
release; the workflow logs a notice saying so. Pushing a version that has
already been released is the same case: bump it again.

## In-app updates

Installed copies check `https://api.github.com/repos/jaym-01/Appy/releases/latest`
on launch. If the release is newer than `__version__`, a bar offers
**Install update**, which downloads the installer to `%TEMP%` and runs it
silently. The installer closes Appy, replaces it, and relaunches it.

Two constraints:

- The asset must be named `AppySetup.exe` and its download URL must sit under
  `github.com/jaym-01/Appy/releases/download/`. Any other URL is ignored, so a
  tampered API response cannot point the installer elsewhere.
- The repository (or at least its releases) must be public. A private repo's
  assets return 404 to the app and the update bar never appears. Workflow
  artifacts cannot serve this purpose either: they need a signed-in session,
  arrive zipped, and expire after 90 days.

Running from source never checks for updates.
