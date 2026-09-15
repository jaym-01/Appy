"""A simulated device, so the WebDAV layer can be tested without hardware.

FakeAfcSession has the same surface as src.device.AfcSession but reads from a
local directory. It counts stats, which is how the cache is tested.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

# Explorer sniffs content, not extension, so the fake JPEGs carry real magic bytes.
JPEG_MAGIC = b"\xff\xd8\xff\xe0"
JPEG_TAIL = b"\xff\xd9"
HIDDEN = ("PhotoData", "MediaAnalysis", "iTunes_Control", "Purchases")


def build_media_tree(root: Path) -> None:
    """Lay out a directory that mirrors a real iPad's AFC media sandbox."""
    for folder, count in (("100APPLE", 4), ("118APPLE", 6)):
        d = root / "DCIM" / folder
        d.mkdir(parents=True)
        for i in range(count):  # varied sizes, so size and partial-read assertions mean something
            body = bytes((i * 7 + j) % 256 for j in range(1024 * (i + 1)))
            (d / f"IMG_{8000 + i:04d}.JPG").write_bytes(JPEG_MAGIC + body + JPEG_TAIL)
        (d / "IMG_9000.MOV").write_bytes(b"\x00" * 4096)
    (root / "Downloads").mkdir()
    (root / "Downloads" / "note.txt").write_bytes(b"hello from the device")
    (root / "Books").mkdir()
    for hidden in HIDDEN:  # Photos-database noise the server must hide
        (root / hidden).mkdir()
        (root / hidden / "internal.db").write_bytes(b"x" * 32)
    (root / ".hidden_marker").write_bytes(b"")


class FakeAfcSession:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.closed = False
        self.stat_calls = 0
        self._handles: dict[int, object] = {}

    @property
    def open_handles(self) -> int:
        return len(self._handles)

    def _resolve(self, path: str) -> Path:
        target = (self.root / str(path).replace("\\", "/").lstrip("/")).resolve()
        if not str(target).startswith(str(self.root)):  # AFC's sandbox cannot be escaped
            raise OSError(2, "outside sandbox", path)
        return target

    async def run(self, method: str, *args):
        return getattr(self, method)(*args)

    async def close(self) -> None:
        self.closed = True
        for fh in self._handles.values():
            fh.close()
        self._handles.clear()

    def stat(self, path: str) -> dict:
        self.stat_calls += 1
        target = self._resolve(path)
        if not target.exists():
            raise OSError(2, "No such file or directory", path)
        info = target.stat()
        return {
            "st_ifmt": "S_IFDIR" if target.is_dir() else "S_IFREG",
            "st_size": info.st_size,
            "st_mtime": datetime.fromtimestamp(info.st_mtime),
        }

    def listdir(self, path: str) -> list[str]:
        return sorted(p.name for p in self._resolve(path).iterdir())

    def fopen(self, path: str, mode: str = "r") -> int:
        handle = max(self._handles, default=0) + 1
        self._handles[handle] = self._resolve(path).open("rb")
        return handle

    def fread(self, handle: int, size: int) -> bytes:
        return self._handles[handle].read(size)

    def fseek(self, handle: int, offset: int, whence: int) -> None:
        self._handles[handle].seek(offset, whence)

    def fclose(self, handle: int) -> None:
        self._handles.pop(handle).close()
