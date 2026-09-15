# How it works

Hudzen speaks **AFC** to the device and **WebDAV** to Explorer, and translates
between the two.

```
iPhone / iPad ──USB──▶ usbmuxd ──▶ pymobiledevice3 (AFC) ──▶ Hudzen ──WebDAV──▶ File Explorer
                       (Apple Devices app)                   127.0.0.1:2121
```

## Why not MTP

Windows talks to an iPhone over MTP, the same protocol as a digital camera.
It is slow to enumerate and hides the real filesystem: folders become
synthetic month buckets (`202607_a`) and filenames are scrambled
(`GMJL3587.MP4`).

AFC — Apple File Conduit — is what iTunes uses. It exposes the device's real
media folder with real names, and it is fast: listing ~6,000 files takes
0.35 s against 81 s over MTP.

## Why WebDAV

Explorer has two built-in network clients: FTP and WebDAV.

- **FTP** downloads files correctly but never feeds them into Explorer's
  thumbnail pipeline. That is a limit of Explorer's FTP client and cannot be
  fixed server-side. An early version of Hudzen used FTP.
- **WebDAV**, opened the right way, is treated like a real filesystem:
  thumbnails, preview pane, and search all work.

The alternative — a WinFsp or Dokan filesystem driver — gives a real drive
letter, but needs a kernel-mode install and admin rights, and Explorer's
stat-heavy behaviour makes a ~420 stat/s backend feel broken.

## Why a UNC path and not a drive letter

Windows' WebDAV redirector refuses loopback addresses for mapped drives:
`net use X: http://127.0.0.1:2121/` fails with system error 67, even though
the server is fully compliant.

Opening the same location by its UNC form instead — `\\127.0.0.1@2121\root\`,
passed straight to `explorer.exe` — takes a different code path in the
redirector that has no loopback check. It is also the code path that gets
thumbnails.

The `root` segment exists because the redirector addresses WebDAV like SMB:
`\\host\share\path`. It will not browse `\\host@port\` with nothing after it,
so the provider is mounted at `/root` and that is the browsable top.

## Read-only, twice

- `AfcProvider.is_readonly()` returns `True`, so wsgidav does not even
  dispatch `PUT`, `DELETE`, `MKCOL`, `MOVE`, `LOCK`, or `UNLOCK` to it. A
  write attempt gets `405 Method Not Allowed`.
- No write method is implemented anywhere in `webdav.py`. If a request did
  get through, it would hit wsgidav's base-class default, which raises
  `HTTP_FORBIDDEN`.

The server binds to `127.0.0.1` only and stops when the app closes or the
device is unplugged.

## Modules

| File | Role |
|---|---|
| `src/app.py` | Entry point. Creates the Qt app, the bridge, and the window. |
| `src/device.py` | `scan()` polls usbmux every 2 s for attached devices. `AfcSession` is the file connection to one device, rebuilt automatically when the USB link drops. |
| `src/webdav.py` | The read-only WebDAV server: `SyncAfc` (blocking, cached view of a session), `AfcFile` (buffered reads), the wsgidav provider, and `DeviceWebdav` (one server and port per device). |
| `src/bridge.py` | One asyncio loop on a daemon thread. pymobiledevice3 is async; wsgidav, cheroot, and Qt are not. Every device call hops across. |
| `src/update.py` | Checks GitHub Releases for a newer version and runs the installer. Only the frozen build checks. |
| `src/ui/` | The window. `style.py` reads the accent colour and light/dark setting from the registry so it matches Windows 11. |

## Lifecycle

**Startup.** `pymobiledevice3` takes ~1.2 s to import (it pulls in ~900
modules), so it is imported lazily inside `device.scan()` and
`AfcSession.run()`, on the asyncio thread, after the window is already on
screen. Device details are cached per UDID: they cannot change while a device
stays plugged in, and reading them costs a full lockdown handshake.

**A device appears.** The window starts a `DeviceWebdav` on the next free port
from 2121. Its button opens `\\127.0.0.1@<port>\root\` in Explorer.

**A device disappears.** Its server is stopped in dependency order: a
`stopping` flag so in-flight transfers give up, then the cheroot server and its
socket, then the serve thread, then the AFC session the thread was using.

**Shutdown.** `AsyncBridge.shutdown()` cancels outstanding tasks *before*
stopping the loop — stopping first strands queued coroutines and their callers
wait out the full timeout — then closes the loop so the Windows proactor
releases its sockets.

**Link drops.** The USB link is not durable; the device falls off usbmux when
it auto-locks or the cable is nudged. `AfcSession` retries every operation
through a fresh session (3 attempts, growing backoff), so a disconnect behaves
as a pause rather than a failure. An `AfcException` (missing or unreadable
file) is a result, not a lost link, and is not retried.
