"""
Screen streamer — captures live frames from connected Android device via ADB,
encodes each frame as a JPEG, strips EXIF, and broadcasts over WebSocket.

Served via aiohttp on a single unified port (HTTP UI at / and WS at /ws) so
a single Cloudflare tunnel exposes both.
"""
import asyncio
import subprocess
import logging
import os
import time
from typing import Optional, Set

from aiohttp import web
import aiohttp

from .privacy import strip_exif_from_frame

logger = logging.getLogger("streamer")


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

        self._clients: Set[web.WebSocketResponse] = set()
        self._running  = False
        self._last_frame: Optional[bytes] = None

        # Path to the UI static files
        self._ui_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui")

    # ── Frame capture worker ──────────────────────────────────────────────────

    def _capture_single_frame(self) -> Optional[bytes]:
        """
        Capture a single screen frame via ADB screencap and convert to JPEG
        using FFmpeg. Strips EXIF metadata before returning.
        """
        try:
            # 1. Capture PNG frame over ADB
            p1 = subprocess.run(
                ["adb", "-s", self.serial, "exec-out", "screencap", "-p"],
                capture_output=True,
                timeout=5
            )
            if not p1.stdout or len(p1.stdout) < 100:
                return None

            # 2. Convert PNG to compact JPEG using FFmpeg
            p2 = subprocess.run(
                ["ffmpeg", "-loglevel", "quiet", "-i", "pipe:0",
                 "-vf", "scale=540:-1", "-f", "mjpeg", "-q:v", "6", "pipe:1"],
                input=p1.stdout,
                capture_output=True,
                timeout=5
            )
            if not p2.stdout or len(p2.stdout) < 100:
                return None

            # 3. Strip EXIF metadata for privacy
            return strip_exif_from_frame(p2.stdout)
        except Exception as err:
            logger.debug("Frame capture exception: %s", err)
            return None

    # ── MJPEG frame producer loop ─────────────────────────────────────────────

    async def _frame_producer(self):
        """
        Continuously capture frames from device, cache latest frame,
        and broadcast to all connected WebSocket clients.
        """
        loop = asyncio.get_event_loop()
        logger.info("[%s] Frame producer loop started.", self.serial)

        while self._running:
            try:
                frame = await loop.run_in_executor(None, self._capture_single_frame)
                if frame:
                    self._last_frame = frame
                    if self._clients:
                        dead = set()
                        for ws in list(self._clients):
                            try:
                                await ws.send_bytes(frame)
                            except Exception:
                                dead.add(ws)
                        self._clients -= dead
                else:
                    await asyncio.sleep(0.1)
            except Exception as exc:
                logger.debug("Error in frame producer loop: %s", exc)
                await asyncio.sleep(0.2)

    # ── aiohttp WebSocket handler ─────────────────────────────────────────────

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle a new WebSocket client connection at /ws."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self._clients.add(ws)
        logger.info("WS client connected: %s", request.remote)

        try:
            # Send the latest cached frame immediately so client sees stream at once
            if self._last_frame:
                await ws.send_bytes(self._last_frame)

            # Keep connection open; producer pushes frames to self._clients
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
        """Start combined HTTP+WebSocket aiohttp server and frame producer loop."""
        self._running = True

        app = web.Application()
        app.router.add_get("/ws", self._ws_handler)
        app.router.add_get("/", self._index_handler)
        app.router.add_static("/", self._ui_dir, show_index=False)

        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, self.ws_host, self.ws_port)
        await site.start()

        logger.info(
            "Combined HTTP+WebSocket server listening on http://%s:%d (WS at /ws)",
            self.ws_host, self.ws_port,
        )

        self._runner = runner
        await self._frame_producer()

    def stop(self):
        """Stop frame producer and shutdown server."""
        self._running = False
