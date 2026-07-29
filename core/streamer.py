"""
Screen streamer — captures frames via scrcpy's raw video output piped over
ADB, encodes each frame as a JPEG, strips EXIF, then broadcasts over
WebSocket.

The WebSocket endpoint is served on the SAME port as the HTTP UI server
(via aiohttp) so a single cloudflared tunnel exposes both the viewer page
and the live stream.  Clients connect to  wss://<tunnel-host>/ws  and the
browser auto-detects the correct URL from window.location.
"""
import asyncio
import subprocess
import logging
import os
from typing import Optional, Set

from aiohttp import web
import aiohttp

from .privacy import strip_exif_from_frame

logger = logging.getLogger("streamer")

MAX_FRAME_SIZE = 8 * 1024 * 1024   # 8 MB safety cap per frame


class ScreenStreamer:
    def __init__(
        self,
        serial: str,
        ws_host: str = "0.0.0.0",
        ws_port: int = 8080,          # unified port (HTTP + WS)
        max_size: str = "1280x720",
        bit_rate: str = "4M",
        fps: int = 30,
    ):
        self.serial   = serial
        self.ws_host  = ws_host
        self.ws_port  = ws_port
        self.max_size = max_size
        self.bit_rate = bit_rate
        self.fps      = fps

        self._proc: Optional[subprocess.Popen] = None
        self._clients: Set[web.WebSocketResponse] = set()
        self._running  = False
        self._last_frame: Optional[bytes] = None

        # Path to the UI static files
        self._ui_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui")

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
            stderr=subprocess.PIPE,  # capture errors for debugging
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
                            await ws.send_bytes(clean_frame)
                        except Exception:
                            dead.add(ws)
                    self._clients -= dead

    # ── aiohttp WebSocket handler ─────────────────────────────────────────────

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle a new WebSocket client connection at /ws."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self._clients.add(ws)
        logger.info("WS client connected: %s", request.remote)

        try:
            # Send the latest cached frame immediately so the client
            # doesn't stare at a blank screen on connect.
            if self._last_frame:
                await ws.send_bytes(self._last_frame)

            # Keep connection alive; frames arrive via _frame_producer
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.ERROR:
                    logger.warning("WS error: %s", ws.exception())
                    break
        finally:
            self._clients.discard(ws)
            logger.info("WS client disconnected: %s", request.remote)

        return ws

    # ── aiohttp static file handler ───────────────────────────────────────────

    async def _index_handler(self, request: web.Request) -> web.FileResponse:
        """Serve the UI index.html."""
        return web.FileResponse(os.path.join(self._ui_dir, "index.html"))

    # ── Public API ────────────────────────────────────────────────────────────

    async def start(self):
        """Start scrcpy, ffmpeg, and a combined HTTP+WebSocket aiohttp server."""
        self._running = True

        self._scrcpy_proc = self._start_scrcpy()
        # Small delay to let scrcpy negotiate with the device
        await asyncio.sleep(1.5)

        self._ffmpeg_proc = self._start_ffmpeg(self._scrcpy_proc.stdout)

        # Build aiohttp app — serves UI on / and WebSocket on /ws
        app = web.Application()
        app.router.add_get("/ws", self._ws_handler)
        app.router.add_get("/", self._index_handler)
        app.router.add_static("/", self._ui_dir, show_index=False)

        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, self.ws_host, self.ws_port)
        await site.start()

        logger.info(
            "Combined HTTP+WebSocket server on http://%s:%d  (WS at /ws)",
            self.ws_host, self.ws_port,
        )

        # Store runner so stop() can clean up
        self._runner = runner

        await self._frame_producer()

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
