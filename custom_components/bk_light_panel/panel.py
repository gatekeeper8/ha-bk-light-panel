"""Connection handling for one BK-Light panel through HA's Bluetooth stack.

Works with any Bluetooth adapter Home Assistant has, including ESPHome
Bluetooth proxies with active connections enabled.
"""

from __future__ import annotations

import asyncio
import time
import logging
from collections.abc import Callable
from datetime import datetime

from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later

from .const import IDLE_DISCONNECT_SECONDS, MAX_PIECE_BYTES, RECOVER_DELAYS
from .protocol import FrameNotConfirmed, PanelSession

_LOGGER = logging.getLogger(__name__)


class BkLightPanel:
    """Keeps a connection open while in use, closes it when idle."""

    def __init__(self, hass: HomeAssistant, address: str, name: str) -> None:
        self.hass = hass
        self.address = address.upper()
        self.name = name
        self._lock = asyncio.Lock()
        self._client: BleakClientWithServiceCache | None = None
        self._session: PanelSession | None = None
        self._cancel_idle: Callable[[], None] | None = None
        # time shown by the flip clock last, to animate the next change
        self.last_clock_time: str | None = None
        # last picture on the screen: an identical one is not sent again,
        # because every upload makes the panel redraw (a visible blink)
        self._last_png: bytes | None = None
        # what should be on the screen (kept across a dropped connection)
        self._wanted_png: bytes | None = None
        self._closing = False
        self._shutting_down = False
        self._recover_task: asyncio.Task | None = None
        # per-piece receipts; switched on only if the panel misses pictures without
        self._acknowledged_writes = False
        # what kind of screen is shown ("clock", "readings"; None = anything else)
        self.last_screen: str | None = None
        # (width, height), known after the first handshake
        self.size: tuple[int, int] | None = None

    async def async_get_size(self) -> tuple[int, int]:
        """The panel's size in pixels; connects once to ask if not known yet."""
        if self.size:
            return self.size
        async with self._lock:
            if not self.size:
                try:
                    await self._ensure_connected()
                    assert self._session is not None
                    await self._session.ensure_primed()
                except (BleakError, TimeoutError, EOFError, OSError) as err:
                    await self._disconnect()
                    raise HomeAssistantError(
                        f"Cannot reach {self.name}: {err or type(err).__name__}"
                    ) from err
                self.size = self._session.size or (32, 32)
                _LOGGER.debug("%s is %dx%d pixels", self.name, *self.size)
        return self.size

    @property
    def screen_png(self) -> bytes | None:
        """The picture that should be on the screen now."""
        return self._wanted_png

    async def async_send_png(self, png: bytes, screen: str | None = None) -> None:
        """Send one image, reconnecting once if the link dropped."""
        self.last_screen = screen
        async with self._lock:
            self._stop_idle_timer()
            try:
                if png == self._last_png:
                    _LOGGER.debug("%s already shows this picture, not resent", self.name)
                    return
                for attempt in (1, 2):
                    try:
                        await self._ensure_connected()
                        assert self._session is not None
                        await self._session.send_png(png)
                        self._last_png = self._wanted_png = png
                        return
                    except (BleakError, TimeoutError, EOFError, OSError) as err:
                        _LOGGER.debug("Send to %s failed (attempt %s): %s", self.name, attempt, err)
                        if isinstance(err, FrameNotConfirmed) and not self._acknowledged_writes:
                            _LOGGER.warning(
                                "%s did not confirm a picture sent without receipts; "
                                "using acknowledged writes from now on", self.name,
                            )
                            self._acknowledged_writes = True
                        self._last_png = None  # screen content unknown now
                        await self._disconnect()
                        if attempt == 2:
                            raise HomeAssistantError(
                                f"Sending to {self.name} failed: {err or type(err).__name__}"
                            ) from err
            finally:
                if IDLE_DISCONNECT_SECONDS:
                    self._cancel_idle = async_call_later(
                        self.hass, IDLE_DISCONNECT_SECONDS, self._idle_disconnect
                    )

    async def _ensure_connected(self) -> None:
        if self._client is not None and self._client.is_connected and self._session:
            return
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise HomeAssistantError(
                f"{self.name} ({self.address}) not found. Is it switched on and within "
                "range of a Bluetooth adapter or proxy with active connections?"
            )
        started = time.monotonic()
        self._client = await establish_connection(
            BleakClientWithServiceCache,
            device,
            self.name,
            disconnected_callback=self._on_disconnected,
            max_attempts=3,
        )
        mtu = getattr(self._client, "mtu_size", 23) or 23
        _LOGGER.debug("Connected to %s in %.1f s, MTU %s", self.name, time.monotonic() - started, mtu)
        self._session = PanelSession(
            self._client, max_write=min(mtu - 3, MAX_PIECE_BYTES), acknowledged=self._acknowledged_writes
        )
        await self._session.start()

    @callback
    def _on_disconnected(self, _client: object) -> None:
        _LOGGER.debug("%s disconnected", self.name)
        self._session = None
        if not self._closing:
            # dropped unexpectedly: the panel now plays its stored animations,
            # so reconnect and put our picture back as soon as possible
            self._last_png = None
            if not self._shutting_down and self._wanted_png and (
                self._recover_task is None or self._recover_task.done()
            ):
                self._recover_task = self.hass.async_create_background_task(
                    self._recover(), f"{self.name} reconnect"
                )

    async def _recover(self) -> None:
        for delay in RECOVER_DELAYS:
            await asyncio.sleep(delay)
            if self._shutting_down or self._wanted_png is None:
                return
            if self._last_png == self._wanted_png:
                return  # something else already restored the screen
            try:
                await self.async_send_png(self._wanted_png)
                _LOGGER.debug("%s reconnected, picture restored", self.name)
                return
            except HomeAssistantError as err:
                _LOGGER.debug("%s still unreachable: %s", self.name, err)

    async def _idle_disconnect(self, _now: datetime) -> None:
        self._cancel_idle = None
        async with self._lock:
            await self._disconnect()

    async def _disconnect(self) -> None:
        client, self._client, self._session = self._client, None, None
        if client is not None:
            self._closing = True
            try:
                await client.disconnect()
            except BleakError:
                pass
            finally:
                self._closing = False

    def _stop_idle_timer(self) -> None:
        if self._cancel_idle is not None:
            self._cancel_idle()
            self._cancel_idle = None

    async def async_shutdown(self) -> None:
        self._shutting_down = True
        if self._recover_task is not None:
            self._recover_task.cancel()
        self._stop_idle_timer()
        async with self._lock:
            await self._disconnect()
