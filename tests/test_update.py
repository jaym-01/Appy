"""The update check, against a canned GitHub API response: no network."""

from __future__ import annotations

import asyncio
import io
import json
import sys
import unittest
from unittest import mock

from src import update


def _api(tag: str, assets: list[dict]):
    """Stand-in for update._get returning one canned /releases/latest body."""

    def get(url, accept=None):
        return io.BytesIO(json.dumps({"tag_name": tag, "assets": assets}).encode())

    return get


GOOD = {"name": "AppySetup.exe", "browser_download_url": f"{update._DOWNLOADS}v9.0.0/AppySetup.exe"}


class UpdateCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        # Only the installed build checks, so pretend to be one.
        self.frozen = mock.patch.object(sys, "frozen", True, create=True)
        self.frozen.start()

    def tearDown(self) -> None:
        self.frozen.stop()

    def check(self, tag: str, assets: list[dict]):
        with mock.patch.object(update, "_get", _api(tag, assets)):
            return asyncio.run(update.check())

    def test_newer_release_is_offered(self):
        self.assertEqual(self.check("v9.0.0", [GOOD]), ("9.0.0", GOOD["browser_download_url"]))

    def test_same_or_older_release_is_ignored(self):
        self.assertIsNone(self.check(f"v{update.__version__}", [GOOD]))
        self.assertIsNone(self.check("v0.0.1", [GOOD]))

    def test_asset_outside_this_repo_is_ignored(self):
        bad = dict(GOOD, browser_download_url="https://example.com/AppySetup.exe")
        self.assertIsNone(self.check("v9.0.0", [bad]))

    def test_release_without_installer_is_ignored(self):
        self.assertIsNone(self.check("v9.0.0", [dict(GOOD, name="notes.txt")]))

    def test_source_checkout_never_checks(self):
        self.frozen.stop()
        try:
            with mock.patch.object(update, "_get", side_effect=AssertionError("must not fetch")):
                self.assertIsNone(asyncio.run(update.check()))
        finally:
            self.frozen.start()
