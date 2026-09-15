"""Checks GitHub Releases for a newer version and installs it on request.

Only the installed build checks; running from source never nags. The download
URL comes from the release's asset list but must sit under this repo's own
releases path, so a tampered API response cannot point the installer elsewhere.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from . import __version__

REPO = "jaym-01/Appy"
ASSET = "AppySetup.exe"
_API = f"https://api.github.com/repos/{REPO}/releases/latest"
_DOWNLOADS = f"https://github.com/{REPO}/releases/download/"


def _get(url: str, accept: str = "application/vnd.github+json"):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "Appy", "Accept": accept}), timeout=15
    )


def _parse(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.lstrip("v").split("."))


async def check() -> tuple[str, str] | None:
    """(version, installer url) if a newer release exists, else None."""
    if not getattr(sys, "frozen", False):
        return None

    def fetch():
        with _get(_API) as response:
            release = json.load(response)
        if _parse(release["tag_name"]) <= _parse(__version__):
            return None
        for asset in release.get("assets", []):
            url = asset.get("browser_download_url", "")
            if asset.get("name") == ASSET and url.startswith(_DOWNLOADS):
                return release["tag_name"].lstrip("v"), url
        return None

    return await asyncio.to_thread(fetch)


async def install(url: str) -> None:
    """Download the installer to temp and launch it silently. The caller then
    quits; /CLOSEAPPLICATIONS lets Setup close Appy itself if it is still up,
    and the installer relaunches it when done."""

    def run():
        path = Path(tempfile.gettempdir()) / ASSET
        with _get(url, "application/octet-stream") as response, open(path, "wb") as out:
            shutil.copyfileobj(response, out)
        subprocess.Popen([str(path), "/SILENT", "/CLOSEAPPLICATIONS"])

    await asyncio.to_thread(run)
