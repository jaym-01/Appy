"""One asyncio loop on a daemon thread, shared by everything that talks to a device.

pymobiledevice3 is async; wsgidav/cheroot and Qt are not. Every device call is
submitted here and waited on from whichever thread made it.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from typing import Any, Coroutine

logger = logging.getLogger(__name__)


class AsyncBridge:
    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="afc-loop", daemon=True)
        self._thread.start()
        self.submit(asyncio.sleep(0)).result(timeout=5)  # wait until the loop is spinning

    def submit(self, coro: Coroutine[Any, Any, Any]) -> concurrent.futures.Future:
        """Schedule a coroutine on the loop thread. Thread-safe."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def shutdown(self) -> None:
        # Cancel before stopping: a stopped loop strands queued coroutines, and
        # anyone blocked on their futures waits out the full timeout.
        def cancel_all() -> None:
            for task in asyncio.all_tasks(self._loop):
                task.cancel()
            self._loop.stop()

        self._loop.call_soon_threadsafe(cancel_all)
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            logger.warning("asyncio loop thread did not exit")
            return
        self._loop.close()  # the Windows proactor holds sockets open until closed
