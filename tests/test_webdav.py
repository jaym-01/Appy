"""End-to-end tests for the WebDAV bridge, driven by a simulated device.

A real wsgidav/cheroot server on a real socket, spoken to with plain HTTP -
PROPFIND, GET (with Range), PUT, DELETE, MKCOL, MOVE - the same requests
Explorer's WebDAV client sends. Only the device underneath is fake.
"""

from __future__ import annotations

import contextlib
import http.client
import io
import logging
import socket
import tempfile
import threading
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

from src.bridge import AsyncBridge
from src.webdav import HOST, SHARE, AfcFile, DeviceWebdav, SyncAfc, norm

from .fake_device import HIDDEN, JPEG_MAGIC, FakeAfcSession, build_media_tree

logging.getLogger("wsgidav").setLevel(logging.CRITICAL)
logging.getLogger("cheroot").setLevel(logging.CRITICAL)

DAV = "{DAV:}"


def free_port() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def share(path: str) -> str:
    """Device-relative path -> path under the /root share the provider is mounted at."""
    return f"/{SHARE}" if path == "/" else f"/{SHARE}{path}"


def request(port: int, method: str, path: str, headers: dict | None = None, body: bytes | None = None):
    """One raw HTTP request against a device-relative path. Returns (status, headers-by-lowercase-name, body)."""
    conn = http.client.HTTPConnection(HOST, port, timeout=15)
    try:
        conn.request(method, share(path), body=body, headers=headers or {})
        resp = conn.getresponse()
        data = resp.read()
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}, data
    finally:
        conn.close()


def propfind(port: int, path: str, depth: str = "1") -> list[dict]:
    """PROPFIND a path; returns one dict per <response> entry, self included."""
    status, _, body = request(port, "PROPFIND", path, headers={"Depth": depth})
    assert status == 207, (status, body)
    root = ET.fromstring(body)
    entries = []
    for resp in root.findall(f"{DAV}response"):
        prop = resp.find(f"{DAV}propstat/{DAV}prop")
        size = prop.findtext(f"{DAV}getcontentlength")
        entries.append({
            "href": unquote(resp.findtext(f"{DAV}href")),
            "is_dir": prop.find(f"{DAV}resourcetype/{DAV}collection") is not None,
            "size": int(size) if size is not None else None,
        })
    return entries


def clean(href: str) -> str:
    return href.rstrip("/") or "/"


def basename(href: str) -> str:
    return clean(href).rsplit("/", 1)[-1]


def children(port: int, path: str) -> list[dict]:
    """Like propfind(), but with the collection's own entry filtered out."""
    want = clean(share(path))
    return [e for e in propfind(port, path) if clean(e["href"]) != want]


class ServerTest(unittest.TestCase):
    """A fresh simulated device and server for every test."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        build_media_tree(self.root)
        self.bridge = AsyncBridge()
        self.session = FakeAfcSession(self.root)
        self.port = free_port()
        self.server = DeviceWebdav(self.bridge, "FAKE", self.port, session=self.session)
        self.server.start()

    def tearDown(self) -> None:
        self.server.stop()
        self.bridge.shutdown()
        self._tmp.cleanup()

    def download(self, path: str, headers: dict | None = None):
        return request(self.port, "GET", path, headers=headers)

    # -- listing ------------------------------------------------------------

    def test_list_returns_entries(self):
        # Regression check for the WebDAV equivalent of the old FTP bug: a
        # folder view must actually enumerate AFC's children, not come back empty.
        entries = children(self.port, "/DCIM/118APPLE")
        self.assertEqual(len(entries), 7, entries)
        names = {basename(e["href"]) for e in entries}
        self.assertIn("IMG_8000.JPG", names)
        sizes = {basename(e["href"]): e["size"] for e in entries}
        self.assertEqual(sizes["IMG_8000.JPG"], 1030)  # real size, not zero

    def test_hidden_directories_are_filtered(self):
        entries = children(self.port, "/")
        names = {basename(e["href"]) for e in entries}
        self.assertTrue({"DCIM", "Downloads"} <= names)
        self.assertFalse(names & {*HIDDEN, ".hidden_marker"})

    def test_directories_are_navigable(self):
        entries = children(self.port, "/DCIM/100APPLE")
        names = {basename(e["href"]) for e in entries}
        self.assertIn("IMG_8000.JPG", names)

    def test_second_listing_costs_no_device_calls(self):
        children(self.port, "/DCIM/118APPLE")
        after_first = self.session.stat_calls
        self.assertGreater(after_first, 0)
        self.assertEqual(len(children(self.port, "/DCIM/118APPLE")), 7)
        self.assertEqual(self.session.stat_calls, after_first, "second listing hit the device")

    def test_propfind_omits_lock_properties(self):
        # lock_storage: False means no lock manager is configured, so LOCK/
        # UNLOCK stay unreachable (already true via is_readonly()) and every
        # entry's property list skips the lockdiscovery/supportedlock XML
        # that would otherwise be built - and thrown away - for each of them.
        _, _, body = request(self.port, "PROPFIND", "/DCIM/118APPLE", headers={"Depth": "1"})
        text = body.decode()
        self.assertNotIn("lockdiscovery", text)
        self.assertNotIn("supportedlock", text)

    # -- transfer -------------------------------------------------------------

    def test_download_matches_source_bytes(self):
        status, _, body = self.download("/DCIM/118APPLE/IMG_8002.JPG")
        self.assertEqual(status, 200)
        self.assertEqual(body, (self.root / "DCIM/118APPLE/IMG_8002.JPG").read_bytes())
        self.assertTrue(body.startswith(JPEG_MAGIC))

    def test_many_small_reads_match_source_bytes(self):
        # Exercises AfcFile's buffer-offset tracking directly: wsgidav asks
        # for 8KB at a time by default, many times per 1MB refill, so this
        # drives the exact read pattern that motivated tracking an offset
        # into the buffer instead of slicing it away on every call.
        expected = (self.root / "DCIM/118APPLE/IMG_8002.JPG").read_bytes()
        afc = SyncAfc(self.bridge, self.session)
        f = AfcFile(afc, "/DCIM/118APPLE/IMG_8002.JPG")
        chunks = []
        while True:
            chunk = f.read(97)  # an odd size, so refills land mid-buffer
            if not chunk:
                break
            chunks.append(chunk)
        f.close()
        self.assertEqual(b"".join(chunks), expected)

    def test_download_larger_than_read_chunk(self):
        payload = bytes(range(256)) * 12000  # ~3MB, so the 1MB buffering path is exercised
        (self.root / "DCIM" / "big.bin").write_bytes(payload)
        status, _, body = self.download("/DCIM/big.bin")
        self.assertEqual(status, 200)
        self.assertEqual(body, payload)

    def test_partial_read_with_range(self):
        # Windows reads a file's opening bytes via a Range request to pull out
        # an embedded thumbnail, so a broken seek shows up as missing thumbnails.
        expected = (self.root / "DCIM/118APPLE/IMG_8003.JPG").read_bytes()
        status, headers, body = self.download(
            "/DCIM/118APPLE/IMG_8003.JPG", headers={"Range": "bytes=1000-"}
        )
        self.assertEqual(status, 206)
        self.assertEqual(body, expected[1000:])

    def test_content_length_matches_real_size(self):
        status, headers, _ = request(self.port, "HEAD", "/DCIM/118APPLE/IMG_8001.JPG")
        self.assertEqual(status, 200)
        self.assertEqual(
            int(headers["content-length"]),
            (self.root / "DCIM/118APPLE/IMG_8001.JPG").stat().st_size,
        )

    def test_handles_are_released_after_download(self):
        # fclose() runs from inside the response generator's `finally`, one AFC
        # round trip after the last body byte is already on the wire - so the
        # client may see the response complete slightly before the handle is
        # actually released. Unlike FTP's control-channel "226 Transfer
        # complete", HTTP has no ack that fires after the server-side cleanup.
        self.download("/DCIM/100APPLE/IMG_8000.JPG")
        deadline = time.monotonic() + 2.0
        while self.session.open_handles and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(self.session.open_handles, 0, "an AFC file handle was left open")

    # -- read-only ------------------------------------------------------------

    def test_writes_are_rejected(self):
        # AfcProvider.is_readonly() makes wsgidav drop PUT/DELETE/MKCOL/MOVE
        # from the set of methods it will even dispatch for this share, so
        # these come back 405 (Method Not Allowed) rather than reaching - and
        # being refused by - the read-only DAVCollection/DAVNonCollection
        # defaults underneath.
        status, _, _ = request(self.port, "PUT", "/DCIM/evil.txt", body=b"x")
        self.assertEqual(status, 405)
        status, _, _ = request(self.port, "DELETE", "/Downloads/note.txt")
        self.assertEqual(status, 405)
        status, _, _ = request(self.port, "MKCOL", "/DCIM/newdir")
        self.assertEqual(status, 405)
        status, _, _ = request(
            self.port, "MOVE", "/Downloads/note.txt",
            headers={"Destination": f"http://{HOST}:{self.port}{share('/Downloads/renamed.txt')}"},
        )
        self.assertEqual(status, 405)
        self.assertFalse((self.root / "DCIM" / "evil.txt").exists())
        self.assertFalse((self.root / "DCIM" / "newdir").exists())
        self.assertTrue((self.root / "Downloads" / "note.txt").exists())

    # -- teardown ---------------------------------------------------------------

    def test_stop_releases_the_port_and_session(self):
        children(self.port, "/")
        self.server.stop()
        self.assertTrue(self.session.closed)
        with socket.socket() as s:  # must be reusable at once, or a reconnect would fail
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((HOST, self.port))

    def test_stop_with_a_client_still_connected(self):
        conn = http.client.HTTPConnection(HOST, self.port, timeout=15)
        conn.request("GET", share("/"))
        conn.getresponse().read()
        self.server.stop()  # unplugging closes the server under an open client; must not hang
        self.assertTrue(self.session.closed)
        conn.close()

    def test_stop_during_transfer_is_prompt(self):
        (self.root / "DCIM" / "huge.bin").write_bytes(b"\x00" * (24 * 1024 * 1024))
        started = threading.Event()

        def pull():
            try:
                conn = http.client.HTTPConnection(HOST, self.port, timeout=15)
                conn.request("GET", share("/DCIM/huge.bin"))
                resp = conn.getresponse()
                while resp.read(4096):
                    started.set()
            except Exception:
                pass  # the transfer is expected to be cut off
            finally:
                conn.close()

        thread = threading.Thread(target=pull, daemon=True)
        thread.start()
        self.assertTrue(started.wait(timeout=15), "transfer never started")
        began = time.monotonic()
        # Cutting the transfer off mid-stream makes cheroot's WSGI gateway try
        # (and fail) to report a 500 after it has already started sending a
        # 206 - a real but harmless race, logged straight to stderr rather
        # than through `logging`. Expected here; not worth silencing in
        # production code, so just swallow it locally.
        with contextlib.redirect_stderr(io.StringIO()):
            self.server.stop()
            # Without the stopping flag the serve thread stays blocked in an
            # AFC call and the join burns its full timeout.
            self.assertLess(time.monotonic() - began, 6.0)
            self.assertTrue(self.session.closed)
            thread.join(timeout=5)


class NormTest(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(norm("/DCIM/118APPLE\\IMG_8000.JPG"), "/DCIM/118APPLE/IMG_8000.JPG")
        self.assertEqual(norm("//DCIM///100APPLE"), "/DCIM/100APPLE")
        self.assertEqual(norm(""), "/")


if __name__ == "__main__":
    unittest.main()
