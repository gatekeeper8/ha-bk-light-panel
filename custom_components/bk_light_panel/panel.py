"""Connection handling for one BK-Light panel through HA's Bluetooth stack.

Works with any Bluetooth adapter Home Assistant has, including ESPHome
Bluetooth proxies with active connections enabled.
"""

from __future__ import annotations

import asyncio
import binascii
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

from .const import (
    ACKNOWLEDGED_MINUTES,
    FAST_WRITES,
    IDLE_DISCONNECT_SECONDS,
    MAX_PIECE_BYTES,
    RECOVER_DELAYS,
    UNCONFIRMED_LIMIT,
    UPLOAD_RETRY_HOURS,
)
from .protocol import FrameNotConfirmed, PanelSession, brightness_command, playlist_command

_LOGGER = logging.getLogger(__name__)


class UploadRefused(HomeAssistantError):
    """The panel did not confirm a stored animation (e.g. too big for it)."""


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
        self._acknowledged_writes = not FAST_WRITES
        self._unconfirmed_in_row = 0  # pictures missed in a row without receipts
        self._acknowledged_since = 0.0
        self._stored: dict[int, int] = {}  # slot -> CRC of the GIF stored there
        # called with the slot -> CRC map after every upload (saved across restarts)
        self.on_stored_change: Callable[[dict[int, int]], None] | None = None
        self._failed_uploads: dict[int, float] = {}  # slot -> when the panel refused it
        self._brightness: int | None = None  # the panel's own brightness now (None = unknown)
        self._wanted_brightness: int | None = None  # set by set_brightness
        # stored slots the panel plays now, and the ones it should play whenever no
        # live picture is shown (also while disconnected); None = unknown / not managed
        self._playlist: list[int] | None = None
        self._background: list[int] | None = None
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
                        await self._apply_state(self._session)
                        await self._session.send_png(png)
                        self._last_png = self._wanted_png = png
                        self._unconfirmed_in_row = 0
                        return
                    except (BleakError, TimeoutError, EOFError, OSError) as err:
                        _LOGGER.debug("Send to %s failed (attempt %s): %s", self.name, attempt, err)
                        if isinstance(err, FrameNotConfirmed) and not self._acknowledged_writes:
                            self._unconfirmed_in_row += 1
                            if self._unconfirmed_in_row >= UNCONFIRMED_LIMIT:
                                _LOGGER.warning(
                                    "%s missed %d pictures in a row sent without receipts; "
                                    "using acknowledged writes for %d minutes",
                                    self.name, self._unconfirmed_in_row, ACKNOWLEDGED_MINUTES,
                                )
                                self._acknowledged_writes = True
                                self._acknowledged_since = time.monotonic()
                                self._unconfirmed_in_row = 0
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

    async def _session_call(self, what: str, call) -> None:
        """Run call(session) with the lock held; reconnect and retry once."""
        async with self._lock:
            self._stop_idle_timer()
            for attempt in (1, 2):
                try:
                    await self._ensure_connected()
                    assert self._session is not None
                    await call(self._session)
                    return
                except (BleakError, TimeoutError, EOFError, OSError) as err:
                    _LOGGER.debug("%s on %s failed (attempt %s): %s", what, self.name, attempt, err)
                    await self._disconnect()
                    if attempt == 2:
                        raise HomeAssistantError(f"{what} on {self.name} failed: {err or type(err).__name__}") from err

    # ------------------------------------------------------ stored animations
    def load_stored(self, slots: dict) -> None:
        """What earlier runs stored in the panel's slots (slot -> CRC)."""
        self._stored = {int(slot): int(crc) for slot, crc in slots.items()}

    def is_stored(self, slot: int, gif: bytes) -> bool:
        return self._stored.get(slot) == binascii.crc32(gif)

    def upload_refused_recently(self, slot: int) -> bool:
        """The panel did not confirm this slot's upload within UPLOAD_RETRY_HOURS."""
        when = self._failed_uploads.get(slot)
        return when is not None and time.monotonic() - when < UPLOAD_RETRY_HOURS * 3600

    def _remember(self, slot: int, crc: int | None) -> None:
        if crc is None:
            self._stored.pop(slot, None)
        else:
            self._stored[slot] = crc
        if self.on_stored_change is not None:
            self.on_stored_change(dict(self._stored))

    async def _upload(self, session: PanelSession, gif: bytes, slot: int, force: bool) -> bool:
        """Store a GIF unless the slot already holds exactly it. True if uploaded."""
        crc = binascii.crc32(gif)
        if not force and self._stored.get(slot) == crc:
            return False
        self._remember(slot, None)  # half-written until the panel confirms
        try:
            await session.send_gif(gif, slot)
        except FrameNotConfirmed as err:
            # not retried: a GIF the panel cannot take would fail again. Drop the
            # link so the panel discards the half-received data.
            self._failed_uploads[slot] = time.monotonic()
            await self._disconnect()
            raise UploadRefused(
                f"{self.name} did not confirm the animation for slot {slot} ({len(gif)} bytes)"
            ) from err
        self._failed_uploads.pop(slot, None)
        self._remember(slot, crc)
        _LOGGER.debug("%s: stored %d bytes of animation in slot %d", self.name, len(gif), slot)
        return True

    async def _command(self, session: PanelSession, data: bytes) -> None:
        """A playlist / brightness command; an unconfirmed one is not retried (no loops)."""
        try:
            await session.command(data)
        except FrameNotConfirmed as err:
            _LOGGER.debug("%s: %s", self.name, err)

    def _brightness_target(self) -> int | None:
        """The brightness live pictures want; 100 if only an animation changed it."""
        if self._wanted_brightness is not None:
            return self._wanted_brightness
        return 100 if self._brightness not in (None, 100) else None

    async def _apply_state(self, session: PanelSession) -> None:
        """Before a live picture: the background playlist and the wanted brightness.

        Usually nothing to do; after a stored animation it switches the playlist
        back (so a dropped connection shows the background, not the last
        animation) and undoes the animation's brightness.
        """
        if self._background and self._playlist != self._background:
            await self._command(session, playlist_command(self._background))
            self._playlist = list(self._background)
        target = self._brightness_target()
        if target is not None and self._brightness != target:
            await self._command(session, brightness_command(target))
            self._brightness = target

    async def async_play_stored(
        self, gif: bytes, slot: int, brightness: int = 100, force: bool = False
    ) -> bool:
        """Let the panel play a GIF from its own memory; uploads it only if the slot differs.

        brightness: % of the panel brightness live pictures use, applied with the
        panel's own brightness (the GIF keeps full colour, so it stays the same
        bytes and is not uploaded again). Undone before the next live picture.
        Returns True if the GIF was uploaded.
        """
        base = self._wanted_brightness if self._wanted_brightness is not None else 100
        level = max(0, min(100, round(base * brightness / 100)))
        uploaded = False

        async def run(session: PanelSession) -> None:
            nonlocal uploaded
            if level != self._brightness:  # dim first: no bright flash of the animation
                await self._command(session, brightness_command(level))
                self._brightness = level
            # playlist first, then the data, as the phone app does
            await session.command(playlist_command([slot]))
            self._playlist = [slot]
            uploaded = await self._upload(session, gif, slot, force) or uploaded

        try:
            await self._session_call("Playing a stored animation", run)
        finally:
            # the screen no longer shows the last live picture: send it again next
            # time, and a reconnect must not cover the animation with it
            self._last_png = self._wanted_png = None
            self.last_screen = "animation"
        return uploaded

    async def async_store_animation(self, gif: bytes, slot: int, play: bool = True, force: bool = False) -> bool:
        """Store a GIF in a slot (skipped if the slot already holds it), and play it.

        Returns True if the GIF was uploaded. The panel then plays it by itself,
        also while disconnected, until the next live picture.
        """
        uploaded = False

        async def run(session: PanelSession) -> None:
            nonlocal uploaded
            if play:
                await session.command(playlist_command([slot]))
                self._playlist = [slot]
            uploaded = await self._upload(session, gif, slot, force) or uploaded

        await self._session_call("Storing an animation", run)
        if play:
            self._last_png = self._wanted_png = None
            self.last_screen = "animation"
        return uploaded

    async def async_set_playlist(self, slots: list[int]) -> None:
        """Play these stored slots in turn; they also show whenever no live picture is
        sent, e.g. while disconnected (the background)."""
        await self._session_call("Setting the playlist", lambda s: s.command(playlist_command(slots)))
        self._playlist = self._background = list(slots)
        self._last_png = None

    async def async_set_brightness(self, level: int) -> None:
        """The panel's own brightness, 0-100 (pixels keep their full colour)."""
        self._wanted_brightness = level
        if self._brightness == level:
            return
        await self._session_call("Setting brightness", lambda s: s.command(brightness_command(level)))
        self._brightness = level

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
        if (FAST_WRITES and self._acknowledged_writes
                and time.monotonic() - self._acknowledged_since > ACKNOWLEDGED_MINUTES * 60):
            _LOGGER.debug("%s: trying writes without receipts again", self.name)
            self._acknowledged_writes = False
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
