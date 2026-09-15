"""Talking to Apple devices over USB. Two halves:

1. ``scan()`` asks usbmux (the service the Apple Devices app installs) which
   devices are plugged in, and reads each one's name and model.
2. ``AfcSession`` is the file connection to one of those devices. AFC is the
   protocol iTunes uses; it exposes the device's media folder.

pymobiledevice3 is imported inside the functions that need it, not at the top:
it takes ~1.2s to import, and the window should be on screen before that cost
is paid.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

POLL_MS = 2000  # how often the window asks scan() what is plugged in

# Photos-database internals that AFC exposes but nobody wants to browse.
HIDDEN_DIRS = frozenset({"PhotoData", "MediaAnalysis",
                        "iTunes_Control", "Purchases"})


# -- finding devices ----------------------------------------------------------


@dataclass(frozen=True)
class Device:
    udid: str
    name: str      # the owner's label
    subtitle: str  # e.g. "iPad Air 11-inch · iOS 26.3.1"
    is_tablet: bool = True


# Details cannot change while a device stays plugged in, but reading them costs
# a full lockdown handshake, so they are cached per UDID until it disappears.
_details: dict[str, Device] = {}


async def scan() -> list[Device]:
    """Every USB-attached Apple device. Polled every 2s rather than subscribed:
    a usbmux Listen subscription holds a socket open for the life of the app
    and must be rebuilt whenever the daemon restarts."""
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.usbmux import list_devices

    found: list[Device] = []
    for mux in await list_devices():
        if not mux.is_usb:
            continue
        if mux.serial in _details:
            found.append(_details[mux.serial])
            continue
        try:
            ld = await create_using_usbmux(serial=mux.serial)
            model = ld.display_name or ld.product_type or "Apple device"
            device = Device(
                udid=mux.serial,
                name=ld.all_values.get(
                    "DeviceName") or ld.display_name or mux.serial,
                subtitle=f"{model} · iOS {ld.product_version or '?'}",
                is_tablet=(ld.all_values.get("DeviceClass")
                           or "iPad").lower() != "iphone",
            )
            _details[mux.serial] = device
        except Exception:
            # Locked or untrusted: still show it, but do not cache, so the next
            # poll picks up the real details once it is unlocked.
            logger.debug("could not read %s", mux.serial, exc_info=True)
            device = Device(mux.serial, "Locked device",
                            "Unlock it and tap Trust")
        found.append(device)

    for udid in set(_details) - {d.udid for d in found}:
        del _details[udid]
    return found


# -- talking to one device ----------------------------------------------------


class DeviceLost(Exception):
    """The device stayed unreachable past the retry budget."""


class AfcSession:
    """One AFC connection, rebuilt automatically when the link drops.

    The USB link is not durable: the device falls off usbmux when it auto-locks
    or the cable is disturbed. Every operation retries through a fresh session,
    so a disconnect behaves as a pause rather than a failure."""

    def __init__(self, udid: str, retries: int = 3, backoff: float = 0.7) -> None:
        self.udid = udid
        self._afc: Any = None  # pymobiledevice3 AfcService, once connected
        self._retries = retries
        self._backoff = backoff
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        afc, self._afc = self._afc, None
        if afc is not None:
            try:
                await afc.aclose()
            except Exception:
                logger.debug("error closing AFC", exc_info=True)

    async def run(self, method: str, *args: Any) -> Any:
        """Call one AfcService method by name, e.g. run("stat", "/DCIM")."""
        from pymobiledevice3.exceptions import AfcException
        from pymobiledevice3.lockdown import create_using_usbmux
        from pymobiledevice3.services.afc import AfcService

        async with self._lock:
            last: BaseException | None = None
            for attempt in range(self._retries):
                try:
                    if self._afc is None:
                        afc = AfcService(await create_using_usbmux(serial=self.udid))
                        await afc.connect()
                        self._afc = afc
                    return await getattr(self._afc, method)(*args)
                except AfcException:
                    raise  # a missing or unreadable file is a result, not a lost link
                except Exception as exc:
                    last = exc
                    logger.debug("AFC %s failed, rebuilding session",
                                 method, exc_info=True)
                    await self.close()
                    await asyncio.sleep(self._backoff * (attempt + 1))
            raise DeviceLost(str(last)) from last
