"""BK-Light LED panel (Action ACT1026 / ACT1025) Bluetooth protocol.

Protocol details are based on Bk-Light-AppBypass by Puparia (MIT License),
https://github.com/Pupariaa/Bk-Light-AppBypass

This module has no Home Assistant imports, so it can be tested on its own.
The session works with any object offering the Bleak client methods
`write_gatt_char(uuid, data, response)` and `start_notify(uuid, callback)`.
"""

from __future__ import annotations

import asyncio
import time
import binascii
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

UUID_WRITE = "0000fa02-0000-1000-8000-00805f9b34fb"
UUID_NOTIFY = "0000fa03-0000-1000-8000-00805f9b34fb"

HANDSHAKE_FIRST = bytes.fromhex("08 00 01 80 0E 06 32 00")
HANDSHAKE_SECOND = bytes.fromhex("04 00 05 80")
FRAME_VALIDATION = bytes.fromhex("05 00 00 01 00")
# Bk-Light-AppBypass sends FRAME_VALIDATION after every 30 frames. On the
# ACT1026 that command makes the panel briefly play the animations stored by
# its phone app (answer 05 00 00 01 03), which shows at night as a flash every
# 30th frame. Frames display fine without it, so it is off (None) by default.
VALIDATION_EVERY: int | None = None

ACK_TIMEOUT = 5.0
STEP_DELAY = 0.2


# Frame kinds (third byte), from the phone app's traffic
KIND_TEXT, KIND_PNG, KIND_GIF = 0x00, 0x02, 0x03
LIVE_SLOT = 0x65  # pictures sent to slot 101 are shown at once and not stored


def build_frame(data: bytes, kind: int = KIND_PNG, mode: int = 0x00, slot: int = LIVE_SLOT) -> bytes:
    """Wrap an image in the panel's frame header.

    total length (2) | kind (1) | 00 00 | data length (4) | CRC-32 of data (4)
    | mode (1) | slot (1) | data.   PNG: mode 0, slot 101 (live picture).
    GIF: mode 2, slot 1..n (stored, played by the panel itself).
    """
    frame = bytearray()
    frame += (len(data) + 15).to_bytes(2, "little")
    frame.append(kind)
    frame += b"\x00\x00"
    frame += len(data).to_bytes(4, "little")
    frame += binascii.crc32(data).to_bytes(4, "little")
    frame += bytes((mode, slot))
    frame += data
    return bytes(frame)


def playlist_command(slots: list[int]) -> bytes:
    """Which stored slots the panel plays, in turn: 08 80 + count + slots."""
    body = b"\x08\x80" + len(slots).to_bytes(2, "little") + bytes(slots)
    return (len(body) + 2).to_bytes(2, "little") + body


def brightness_command(level: int) -> bytes:
    """The panel's own brightness, 0..100."""
    return bytes((0x05, 0x00, 0x04, 0x80, max(0, min(100, int(level)))))


def chunk(data: bytes, size: int) -> list[bytes]:
    """Split data into BLE-write-sized pieces."""
    size = max(20, size)
    return [data[i : i + size] for i in range(0, len(data), size)]


def is_ack_stage_one(payload: bytes) -> bool:
    # 32x32: 0C 00 01 80 81 ..., 64x16: 0B 00 01 80 83 ...
    return len(payload) >= 4 and payload[0] in (0x0B, 0x0C) and payload[1:4] == b"\x00\x01\x80"


def is_ack_stage_two(payload: bytes) -> bool:
    return len(payload) >= 4 and payload[:4] == b"\x08\x00\x05\x80"


def is_ack_frame(payload: bytes) -> bool:
    """05 00 02 00 03 for a picture, 05 00 03 00 03 for a stored animation."""
    return len(payload) == 5 and payload[:2] == b"\x05\x00" and payload[2] in (KIND_PNG, KIND_GIF) \
        and payload[3:] == b"\x00\x03"


def command_ack(payload: bytes) -> int | None:
    """05 00 <command> 80 01: the panel accepted a command (08 playlist, 04 brightness)."""
    if len(payload) == 5 and payload[:2] == b"\x05\x00" and payload[3] == 0x80 and payload[4] == 0x01:
        return payload[2]
    return None


class FrameNotConfirmed(TimeoutError):
    """The panel did not confirm a picture (05 00 02 00 03) in time."""


# pause between unacknowledged pieces, so a proxy's queue is not flooded
PIECE_GAP = 0.02


class PanelSession:
    """One connected panel: handshake once, then send frames."""

    def __init__(self, client: Any, max_write: int = 509, acknowledged: bool = False) -> None:
        self._client = client
        self._max_write = max_write
        # False: pieces go out as write commands (no per-piece receipt); the
        # panel confirms the whole picture anyway. Faster, and avoids GATT
        # write-request timeouts (error 133) seen through ESPHome proxies.
        self.acknowledged = acknowledged
        self._primed = False
        # (width, height) from the first handshake answer: 0C = 32x32, 0B = 64x16
        self.size: tuple[int, int] | None = None
        self._frames_since_validation = 0
        self._stage_one = asyncio.Event()
        self._stage_two = asyncio.Event()
        self._frame_ack = asyncio.Event()
        self._command_acks: dict[int, asyncio.Event] = {}

    async def start(self) -> None:
        await self._client.start_notify(UUID_NOTIFY, self._on_notify)

    def _on_notify(self, _sender: Any, data: bytearray) -> None:
        payload = bytes(data)
        _LOGGER.debug("Panel notification: %s", payload.hex(" "))
        if is_ack_stage_one(payload):
            self.size = (64, 16) if payload[0] == 0x0B else (32, 32)
            self._stage_one.set()
        elif is_ack_stage_two(payload):
            self._stage_two.set()
        elif is_ack_frame(payload):
            self._frame_ack.set()
        elif (command := command_ack(payload)) is not None and command in self._command_acks:
            self._command_acks[command].set()

    async def _write(self, data: bytes, response: bool) -> None:
        await self._client.write_gatt_char(UUID_WRITE, data, response=response)

    async def _handshake(self) -> None:
        self._stage_one.clear()
        await self._write(HANDSHAKE_FIRST, response=False)
        await asyncio.wait_for(self._stage_one.wait(), ACK_TIMEOUT)
        await asyncio.sleep(STEP_DELAY)
        self._stage_two.clear()
        await self._write(HANDSHAKE_SECOND, response=False)
        try:
            await asyncio.wait_for(self._stage_two.wait(), ACK_TIMEOUT)
        except asyncio.TimeoutError:
            # some firmware versions do not answer the second step
            _LOGGER.debug("No answer to second handshake step, continuing")
        await asyncio.sleep(STEP_DELAY)
        self._primed = True

    async def ensure_primed(self) -> None:
        """Handshake once per connection (also tells the panel's size)."""
        if not self._primed:
            await self._handshake()

    async def send_png(self, png_bytes: bytes) -> None:
        """Send one PNG image (must already be the panel's size)."""
        await self._send_frame(build_frame(png_bytes))

    async def send_gif(self, gif_bytes: bytes, slot: int) -> None:
        """Store a GIF animation in a slot; the panel plays it by itself."""
        await self._send_frame(build_frame(gif_bytes, KIND_GIF, mode=0x02, slot=slot))

    async def command(self, data: bytes) -> None:
        """A short command that the panel confirms with 05 00 <command> 80 01."""
        await self.ensure_primed()
        event = self._command_acks.setdefault(data[2], asyncio.Event())
        event.clear()
        await self._write(data, response=self.acknowledged)
        try:
            await asyncio.wait_for(event.wait(), ACK_TIMEOUT)
        except TimeoutError as err:
            raise FrameNotConfirmed(f"panel did not confirm command {data.hex(' ')}") from err
        await asyncio.sleep(STEP_DELAY)

    async def _send_frame(self, frame: bytes) -> None:
        await self.ensure_primed()
        self._frame_ack.clear()
        started = time.monotonic()
        # split to fit the link's MTU (and one radio packet)
        pieces = chunk(frame, self._max_write)
        for i, piece in enumerate(pieces):
            await self._write(piece, response=self.acknowledged)
            if not self.acknowledged and i < len(pieces) - 1:
                await asyncio.sleep(PIECE_GAP)
        written = time.monotonic()
        try:
            await asyncio.wait_for(self._frame_ack.wait(), ACK_TIMEOUT)
        except TimeoutError as err:
            raise FrameNotConfirmed("panel did not confirm the picture") from err
        _LOGGER.debug(
            "Frame %d bytes in %d pieces of max %d (%s): writing %.2f s, panel answer %.2f s",
            len(frame), len(pieces), self._max_write,
            "acknowledged" if self.acknowledged else "write commands",
            written - started, time.monotonic() - written,
        )
        self._frames_since_validation += 1
        if VALIDATION_EVERY and self._frames_since_validation >= VALIDATION_EVERY:
            await self._write(FRAME_VALIDATION, response=False)
            self._frames_since_validation = 0
        await asyncio.sleep(STEP_DELAY)
