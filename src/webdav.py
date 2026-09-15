"""A read-only WebDAV server fronting one device's AFC media sandbox.

Explorer's WebDAV client treats a location reached via the UNC form
`\\\\host@port\\path` like a real filesystem - real thumbnails, a working
preview pane - unlike its FTP client. And, reached that way instead of via a
mapped drive, it is not subject to the redirector's refusal of loopback
addresses (`net use` against 127.0.0.1 fails; opening the UNC path directly
does not). Read-only twice over: no write method is implemented anywhere
below, so every create/delete/move falls through to wsgidav's default, which
raises HTTP_FORBIDDEN, and the provider also reports itself read-only.
"""

from __future__ import annotations

import logging
import posixpath
import threading
import time

from cheroot import wsgi
from wsgidav.dav_provider import DAVCollection, DAVNonCollection, DAVProvider
from wsgidav.wsgidav_app import WsgiDAVApp

from .bridge import AsyncBridge
from .device import HIDDEN_DIRS, AfcSession

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"
BASE_PORT = 2121
SHARE = "root"  # the WebDAV redirector needs a share name; see DeviceWebdav.url
CACHE_TTL = 30.0  # a camera roll barely changes while you browse it
CALL_TIMEOUT = 20.0
READ_CHUNK = 1 << 20  # 1MB per AFC round trip, whatever WebDAV asks for


def norm(path) -> str:
    """A clean POSIX path with no doubled slashes - AFC cannot stat those.
    WebDAV paths come from URL parsing so they are already POSIX, but this is
    cheap insurance against the same class of bug that silently emptied every
    folder under the old FTP server."""
    text = str(path).replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    return text or "/"


def _visible(names) -> list[str]:
    return [n for n in names if n not in (".", "..") and n not in HIDDEN_DIRS and not n.startswith(".")]


class SyncAfc:
    """Blocking, cached view of one AFC session, shared by every WebDAV
    request to the device. A folder view stats every entry and AFC manages
    ~420 stats/s, so listing a directory warms the stat cache for all its
    children at once."""

    def __init__(self, bridge: AsyncBridge, session: AfcSession) -> None:
        self._bridge = bridge
        self._session = session
        self._stat: dict[str, tuple[dict, float]] = {}
        self._dirs: dict[str, tuple[list[str], float]] = {}
        self.stopping = False

    def call(self, method: str, *args):
        if self.stopping:  # the server is about to stop; a queued call would never return
            raise OSError(5, "server is shutting down")
        return self._bridge.submit(self._session.run(method, *args)).result(timeout=CALL_TIMEOUT)

    def stat(self, path: str) -> dict | None:
        path = norm(path)
        hit = self._stat.get(path)
        if hit and time.time() - hit[1] < CACHE_TTL:
            return hit[0]
        try:
            info = self.call("stat", path)
        except Exception:
            return None
        self._stat[path] = (info, time.time())
        return info

    def listdir(self, path: str) -> list[str]:
        path = norm(path)
        hit = self._dirs.get(path)
        if hit and time.time() - hit[1] < CACHE_TTL:
            return hit[0]
        names = _visible(self.call("listdir", path))
        self._dirs[path] = (names, time.time())
        for name in names:
            self.stat(posixpath.join(path, name))
        return names


class AfcFile:
    """Buffered reader over an AFC handle. wsgidav opens one of these per GET,
    seeks it for a Range request, then reads from it in whatever chunks it
    likes; serving each as its own AFC round trip measured 4 MB/s, 1MB reads
    7-10 MB/s."""

    def __init__(self, afc: SyncAfc, path: str) -> None:
        self.name = path
        self.closed = False
        self._afc = afc
        self._pos = 0
        self._buf = b""
        self._buf_pos = 0  # read offset into self._buf, so read() need not slice it on every call
        self._handle = afc.call("fopen", path, "r")

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = READ_CHUNK
        while len(self._buf) - self._buf_pos < size:
            block = self._afc.call("fread", self._handle, READ_CHUNK)
            if not block:
                break
            if self._buf_pos:  # drop what's already been read, only when a refill needs the room
                self._buf = self._buf[self._buf_pos:]
                self._buf_pos = 0
            self._buf += block
        data = self._buf[self._buf_pos:self._buf_pos + size]
        self._buf_pos += len(data)
        self._pos += len(data)
        return data

    def seek(self, offset: int, whence: int = 0) -> int:
        self._buf = b""
        self._buf_pos = 0
        self._afc.call("fseek", self._handle, offset, whence)
        self._pos = offset if whence == 0 else self._pos + offset
        return self._pos

    def tell(self) -> int:
        return self._pos

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            try:
                self._afc.call("fclose", self._handle)
            except Exception:
                logger.debug("error closing AFC handle", exc_info=True)


def _mtime(info: dict) -> float | None:
    stamp = info.get("st_mtime") or info.get("st_birthtime")
    return stamp.timestamp() if hasattr(stamp, "timestamp") else None


class AfcResource(DAVNonCollection):
    """One file. wsgidav calls get_content() once per GET/HEAD, then reads
    from (and, for a Range request, seeks) the object it returns."""

    def __init__(self, path: str, environ: dict, afc: SyncAfc, info: dict) -> None:
        super().__init__(path, environ)
        self._afc = afc
        self._info = info

    def get_content_length(self) -> int:
        return int(self._info.get("st_size", 0))

    def get_last_modified(self):
        return _mtime(self._info)

    def get_etag(self):
        return None

    def support_etag(self) -> bool:
        return False

    def support_ranges(self) -> bool:
        return True

    def get_content(self) -> AfcFile:
        return AfcFile(self._afc, self.path)


class AfcCollection(DAVCollection):
    """One directory. Members come straight from the same cached listing the
    old FTP LIST command used."""

    def __init__(self, path: str, environ: dict, afc: SyncAfc, info: dict) -> None:
        super().__init__(path, environ)
        self._afc = afc
        self._info = info

    def get_member_names(self) -> list[str]:
        return self._afc.listdir(self.path)

    def get_last_modified(self):
        return _mtime(self._info)

    def get_descendants(self, **kwargs):
        # A real device's media library can hold thousands of files. A
        # PROPFIND with no Depth header at all is, per RFC 4918, supposed to
        # be treated as "infinity" - wsgidav does exactly that - which would
        # mean one AFC round trip per file in the entire library with no
        # cache warm yet: minutes, not seconds. Answer as if Depth: 1 had
        # been requested instead - still a normal 207, just scoped to this
        # one folder - rather than refusing outright, since a client that
        # doesn't expect an error on this request may treat the whole share
        # as broken rather than retrying shallower.
        if kwargs.get("depth", "infinity") == "infinity":
            kwargs["depth"] = "1"
        return super().get_descendants(**kwargs)


class AfcProvider(DAVProvider):
    """Maps WebDAV paths straight onto AFC paths. AFC already confines
    everything to /var/mobile/Media, so there is nothing to escape to.

    No write method is implemented anywhere in this file: every create,
    delete, move, and write call falls through to DAVCollection's or
    DAVNonCollection's default implementation, which raises
    DAVError(HTTP_FORBIDDEN)."""

    def __init__(self, afc: SyncAfc) -> None:
        super().__init__()
        self._afc = afc

    def is_readonly(self) -> bool:
        return True

    def get_resource_inst(self, path: str, environ: dict):
        path = norm(path)
        info = self._afc.stat(path)
        if info is None:
            return None
        if info.get("st_ifmt") == "S_IFDIR":
            return AfcCollection(path, environ, self._afc, info)
        return AfcResource(path, environ, self._afc, info)


class DeviceWebdav:
    """One device's AFC session plus the WebDAV server exposing it."""

    def __init__(self, bridge: AsyncBridge, udid: str, port: int, session: AfcSession | None = None) -> None:
        self.udid = udid
        self.port = port
        # The UNC form Explorer opens directly, with no drive letter - and,
        # unlike `net use`, not subject to the redirector's loopback refusal.
        # The redirector addresses a WebDAV location the same way it addresses
        # SMB: \\host\share\path. A share is the minimum addressable unit - it
        # will not browse \\host@port\ with nothing after it, and there is no
        # way to navigate "up" out of a share either. So the provider is
        # mounted at /root below, and this is the actual browsable top: every
        # real folder (DCIM, Downloads, ...) is a normal child of it, reachable
        # by ordinary Explorer navigation in both directions.
        self.url = f"\\\\{HOST}@{port}\\{SHARE}\\"
        self._bridge = bridge
        self._session = session or AfcSession(udid)  # injectable, so tests need no hardware
        self._afc = SyncAfc(bridge, self._session)
        self._server: wsgi.Server | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        config = {
            "host": HOST,
            "port": self.port,
            "provider_mapping": {f"/{SHARE}": AfcProvider(self._afc)},
            "simple_dc": {"user_mapping": {"*": True}},  # anonymous, no login prompt
            "dir_browser": {"enable": False},  # only WebDAV clients use this share, not a browser
            # No lock manager: it defaults on otherwise, and every PROPFIND then
            # carries dead lockdiscovery/supportedlock XML per entry - LOCK and
            # UNLOCK are already unreachable, since is_readonly() excludes them
            # from dispatch regardless.
            "lock_storage": False,
            "verbose": 0,
        }
        app = WsgiDAVApp(config)
        # AFC access is serialized through one lock per device session anyway
        # (see AfcSession), so most of cheroot's default 10 threads could never
        # run a device call concurrently - a handful is enough to cover a
        # folder view plus a couple of thumbnail GETs at once.
        self._server = wsgi.Server((HOST, self.port), app, numthreads=4)
        self._server.prepare()  # binds the socket now, so a busy port raises here, not on the thread
        self._thread = threading.Thread(target=self._server.serve, name=f"webdav-{self.port}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        # Order matters: the flag first so a transfer about to make another
        # AFC call gives up, then the sockets, then the thread, and only then
        # the session the thread was using.
        self._afc.stopping = True
        if self._server is not None:
            self._server.stop()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                logger.warning("WebDAV thread for port %s did not exit", self.port)
            self._thread = None
        try:
            self._bridge.submit(self._session.close()).result(timeout=5)
        except Exception:
            logger.debug("error closing AFC session", exc_info=True)
