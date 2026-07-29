"""
Screen streamer — captures frames via scrcpy's raw video output piped over
ADB, encodes each frame as a JPEG, strips EXIF, then sends over WebSocket.
"""
import asyncio
import subprocess
import struct
import logging
import time
from typing import Optional

import websockets
from websockets.server import WebSocketServerProtocol

from .privacy import strip_exif_from_frame

logger = logging.getLogger("streamer")

# ── scrcpy frame protocol constants ──────────────────────────────────────────
# scrcpy --no-display --raw-stream outputs: [PTS 8 bytes][size 4 bytes][data]
# We read that binary stream directly.
SCRCPY_HEADER_SIZE = 12   # 8 bytes PTS + 4 bytes payload size
MAX_FRAME_SIZE     = 8 * 1024 * 1024  # 8 MB safety cap per frame


class ScreenStreamer:
    def __init__(
        self,
        serial: str,
        ws_host: str = "127.0.0.1",
        ws_port: int = 8765,
        max_size: str = "1280x720",
        bit_rate: str = "4M",
        fps: int = 30,
    ):
        self.serial    = serial
        self.ws_host   = ws_host
        self.ws_port   = ws_port
        self.max_size  = max_size
        self.bit_rate  = bit_rate
        self.fps       = fps

        self._proc: Optional[subprocess.Popen] = None
        self._clients: set[WebSocketServerProtocol] = set()
        self._running  = False
        self._last_frame: Optional[bytes] = None

    # ── scrcpy process ────────────────────────────────────────────────────────

    def _start_scrcpy(self) -> subprocess.Popen:
        """
        Launch scrcpy in raw-stream mode.  The H.264 stream is piped to stdout.
        --no-display      : don't open scrcpy's own window
        --raw-stream      : write raw H.264 NAL units to stdout
        --no-audio        : audio not needed for screen mirror
        --lock-video-orientation 0 : keep portrait
        """
        cmd = [
            "scrcpy",
            "-s", self.serial,
            "--no-display",
            "--raw-stream",
            "--no-audio",
            "--video-codec=h264",
            f"--max-size={self.max_size.split('x')[0]}",
            f"--video-bit-rate={self.bit_rate}",
            f"--max-fps={self.fps}",
            "--lock-video-orientation=0",
        ]
        logger.info("Launching scrcpy: %s", " ".join(cmd))
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    # ── FFmpeg transcoder (H.264 → MJPEG) ────────────────────────────────────

    def _start_ffmpeg(self, scrcpy_stdout) -> subprocess.Popen:
        """
        Pipe scrcpy's raw H.264 stream through ffmpeg to produce individual
        JPEG frames on stdout (MJPEG mux gives us length-prefixed frames).
        """
        cmd = [
            "ffmpeg",
            "-loglevel", "quiet",
            "-f", "h264",
            "-i", "pipe:0",
            "-f", "mjpeg",
            "-q:v", "3",       # JPEG quality (2=best, 31=worst)
            "pipe:1",
        ]
        return subprocess.Popen(
            cmd,
            stdin=scrcpy_stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    # ── MJPEG frame reader ────────────────────────────────────────────────────

    async def _frame_producer(self):
        """
        Read MJPEG frames from ffmpeg stdout, strip EXIF, cache the latest
        frame, and notify all connected WebSocket clients.
        """
        loop = asyncio.get_event_loop()
        ffmpeg = self._ffmpeg_proc

        SOI = b"\xff\xd8"
        EOI = b"\xff\xd9"
        buf = b""

        while self._running:
            try:
                chunk = await loop.run_in_executor(
                    None, ffmpeg.stdout.read, 65536
                )
            except Exception:
                break

            if not chunk:
                await asyncio.sleep(0.01)
                continue

            buf += chunk

            # Extract complete JPEG frames from the buffer
            while True:
                start = buf.find(SOI)
                if start == -1:
                    buf = b""
                    break
                end = buf.find(EOI, start + 2)
                if end == -1:
                    buf = buf[start:]   # keep partial frame
                    break

                frame = buf[start: end + 2]
                buf   = buf[end + 2:]

                # Strip EXIF/GPS metadata
                clean_frame = strip_exif_from_frame(frame)
                self._last_frame = clean_frame

                # Broadcast to all connected clients
                if self._clients:
                    dead = set()
                    for ws in list(self._clients):
                        try:
                            await ws.send(clean_frame)
                        except Exception:
                            dead.add(ws)
                    self._clients -= dead

    # ── WebSocket server ──────────────────────────────────────────────────────

    async def _ws_handler(self, ws: WebSocketServerProtocol):
        """Handle a new WebSocket client connection."""
        self._clients.add(ws)
        logger.info("Client connected: %s", ws.remote_address)
        try:
            # Send the latest cached frame immediately so the client
            # doesn't stare at a blank screen on connect.
            if self._last_frame:
                await ws.send(self._last_frame)
            # Keep the connection alive; frames are pushed by _frame_producer
            await ws.wait_closed()
        finally:
            self._clients.discard(ws)
            logger.info("Client disconnected: %s", ws.remote_address)

    # ── Public API ────────────────────────────────────────────────────────────

    async def start(self):
        """Start scrcpy, ffmpeg, WebSocket server, and frame producer."""
        self._running = True

        self._scrcpy_proc = self._start_scrcpy()
        # Small delay to let scrcpy negotiate with the device
        await asyncio.sleep(1.5)

        self._ffmpeg_proc = self._start_ffmpeg(self._scrcpy_proc.stdout)

        ws_server = await websockets.serve(
            self._ws_handler,
            self.ws_host,
            self.ws_port,
        )
        logger.info(
            "WebSocket server listening on ws://%s:%d", self.ws_host, self.ws_port
        )

        await self._frame_producer()
        ws_server.close()

    def stop(self):
        """Terminate streaming processes."""
        self._running = False
        for proc in (getattr(self, "_ffmpeg_proc", None),
                     getattr(self, "_scrcpy_proc", None)):
            if proc:
                try:
                    proc.terminate()
                except Exception:
                    pass
