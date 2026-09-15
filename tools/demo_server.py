"""Serve a simulated device over WebDAV, for eyeballing Explorer without hardware.

    python tools/demo_server.py

Builds a folder of real JPEGs, serves it through the same WebDAV stack the app
uses, and opens Explorer on it. Ctrl-C stops the server and deletes the folder.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw  # noqa: E402

from src.bridge import AsyncBridge  # noqa: E402
from src.webdav import DeviceWebdav  # noqa: E402
from tests.fake_device import FakeAfcSession  # noqa: E402

PORT = 2200


def make_photo(path: Path, seed: int, size: tuple[int, int] = (1600, 1200)) -> None:
    """A real JPEG with visible structure, so a thumbnail is obviously right."""
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    for y in range(0, size[1], 8):
        shade = (y * 255 // size[1] + seed * 40) % 256
        draw.rectangle([0, y, size[0], y + 8], fill=(shade, (shade * 3) % 256, 200))
    draw.ellipse([size[0] // 4, size[1] // 4, size[0] * 3 // 4, size[1] * 3 // 4], fill=((seed * 60) % 256, 40, 220))
    draw.text((40, 40), f"PHOTO {seed:03d}", fill=(255, 255, 255))
    img.save(path, "JPEG", quality=88)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="appy-demo-"))
    for folder, count, base, size in (("118APPLE", 12, 8000, (1600, 1200)), ("100APPLE", 4, 5000, (640, 480))):
        (tmp / "DCIM" / folder).mkdir(parents=True)
        for i in range(count):
            make_photo(tmp / "DCIM" / folder / f"IMG_{base + i:04d}.JPG", i, size)
    (tmp / "Downloads").mkdir()
    (tmp / "Downloads" / "readme.txt").write_bytes(b"simulated device\n")

    bridge = AsyncBridge()
    server = DeviceWebdav(bridge, "DEMO", PORT, session=FakeAfcSession(tmp))
    server.start()
    print(f"simulated device at {tmp}, serving {server.url}; Ctrl-C to stop")
    subprocess.Popen(["explorer.exe", f"{server.url}DCIM\\118APPLE"])
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        bridge.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
