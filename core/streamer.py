"""
Screen streamer — captures live frames from Android device via ADB screencap,
encodes to JPEG, strips EXIF, and broadcasts over WebSocket with bidirectional control.

Uses fast ADB screencap method that works with all scrcpy versions.
Served via aiohttp on a single unified port (HTTP UI at / and WS at /ws).
"""
import asyncio
import subprocess
import logging
import os
import json
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
        ws_port: int = 8080,
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
        self.target_fps = fps

        self._clients: Set[web.WebSocketResponse] = set()
        self._running  = False
        self._last_frame: Optional[bytes] = None

        # Path to the UI static files
        self._ui_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui")

    # ── Fast frame capture via ADB screencap ──────────────────────────────────

    def _capture_frame(self) -> Optional[bytes]:
        """
        Capture single frame via ADB screencap and convert to JPEG with FFmpeg.
        Fast and reliable method that works with all devices.
        """
        try:
            # Capture PNG via ADB
            p1 = subprocess.run(
                ["adb", "-s", self.serial, "exec-out", "screencap", "-p"],
                capture_output=True,
                timeout=2
            )
            if not p1.stdout or len(p1.stdout) < 100:
                return None

            # Convert PNG to JPEG and resize
            width = self.max_size.split('x')[0]
            p2 = subprocess.run(
                ["ffmpeg", "-loglevel", "quiet", "-i", "pipe:0",
                 "-vf", f"scale={width}:-1", "-f", "mjpeg", "-q:v", "5", "pipe:1"],
                input=p1.stdout,
                capture_output=True,
                timeout=2
            )
            if not p2.stdout or len(p2.stdout) < 100:
                return None

            # Strip EXIF metadata
            return strip_exif_from_frame(p2.stdout)
        except Exception as e:
            logger.debug("Frame capture error: %s", e)
            return None

    # ── Frame producer loop ───────────────────────────────────────────────────

    async def _frame_producer(self):
        """
        Continuously capture frames via ADB screencap and broadcast to clients.
        Simple and reliable method that works with all devices.
        """
        loop = asyncio.get_event_loop()
        frame_count = 0
        frame_delay = 1.0 / self.target_fps  # Target delay between frames

        logger.info("[%s] Frame producer started (ADB screencap method)", self.serial)

        while self._running:
            frame_start = asyncio.get_event_loop().time()
            
            # Capture frame in executor to avoid blocking
            frame = await loop.run_in_executor(None, self._capture_frame)
            
            if frame:
                frame_count += 1
                self._last_frame = frame

                # Log first and periodic frames
                if frame_count == 1:
                    logger.info("First frame captured: %d bytes", len(frame))
                elif frame_count % 100 == 0:
                    logger.info("Frame %d: streaming at ~%d fps", frame_count, self.target_fps)

                # Broadcast to all connected clients
                if self._clients:
                    dead = set()
                    for ws in list(self._clients):
                        try:
                            await ws.send_bytes(frame)
                        except Exception:
                            dead.add(ws)
                    self._clients -= dead
            
            # Maintain target FPS
            frame_time = asyncio.get_event_loop().time() - frame_start
            sleep_time = max(0, frame_delay - frame_time)
            await asyncio.sleep(sleep_time)
        
        logger.info("Frame producer stopped")

    # ── aiohttp WebSocket handler ─────────────────────────────────────────────

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket client at /ws - bidirectional video + control."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self._clients.add(ws)
        logger.info("WS client connected: %s", request.remote)

        try:
            # Send latest frame immediately
            if self._last_frame:
                await ws.send_bytes(self._last_frame)

            # Listen for control messages (touch/key events)
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        await self._handle_control_event(msg.data)
                    except Exception as e:
                        logger.error("Control event error: %s", e)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.warning("WS error: %s", ws.exception())
                    break
        finally:
            self._clients.discard(ws)
            logger.info("WS client disconnected: %s", request.remote)

        return ws

    async def _handle_control_event(self, message: str):
        """Handle touch/mouse/keyboard events from browser."""
        loop = asyncio.get_event_loop()
        
        try:
            event = json.loads(message)
            event_type = event.get("type")
            
            if event_type == "touch":
                x = event.get("x")
                y = event.get("y")
                
                # Validate coordinates
                if x is None or y is None:
                    logger.warning("Invalid touch event - missing coordinates")
                    return
                    
                x = int(x)
                y = int(y)
                action = event.get("action", "tap")
                
                if action == "tap":
                    # Single tap
                    cmd = ["adb", "-s", self.serial, "shell", "input", "tap", str(x), str(y)]
                    await loop.run_in_executor(None, lambda: subprocess.run(cmd, capture_output=True, timeout=1))
                    logger.info("Touch tap at (%d, %d)", x, y)
                    
                elif action == "swipe":
                    # Swipe gesture
                    x2 = int(event.get("x2", x))
                    y2 = int(event.get("y2", y))
                    duration = int(event.get("duration", 100))
                    cmd = ["adb", "-s", self.serial, "shell", "input", "swipe",
                           str(x), str(y), str(x2), str(y2), str(duration)]
                    await loop.run_in_executor(None, lambda: subprocess.run(cmd, capture_output=True, timeout=1))
                    logger.info("Swipe (%d,%d) → (%d,%d)", x, y, x2, y2)
                    
            elif event_type == "key":
                key_code = event.get("code")
                if key_code:
                    cmd = ["adb", "-s", self.serial, "shell", "input", "keyevent", str(key_code)]
                    await loop.run_in_executor(None, lambda: subprocess.run(cmd, capture_output=True, timeout=1))
                    logger.info("Key event: %s", key_code)
                    
            elif event_type == "text":
                text = event.get("text", "")
                if text:
                    text_escaped = text.replace(" ", "%s")
                    cmd = ["adb", "-s", self.serial, "shell", "input", "text", text_escaped]
                    await loop.run_in_executor(None, lambda: subprocess.run(cmd, capture_output=True, timeout=1))
                    logger.info("Text input: %s", text)
                    
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in control event")
        except ValueError as e:
            logger.error("Control event value error: %s", e)
        except Exception as e:
            logger.error("Control event processing error: %s", e)

    # ── aiohttp handlers ──────────────────────────────────────────────────────

    async def _index_handler(self, request: web.Request) -> web.FileResponse:
        """Serve the UI index.html."""
        return web.FileResponse(os.path.join(self._ui_dir, "index.html"))

    # ── Public API ────────────────────────────────────────────────────────────

    async def start(self):
        """Start aiohttp server and frame producer using ADB screencap."""
        self._running = True

        # Start aiohttp HTTP + WebSocket server
        app = web.Application()
        app.router.add_get("/ws", self._ws_handler)
        app.router.add_get("/", self._index_handler)
        app.router.add_static("/", self._ui_dir, show_index=False)

        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, self.ws_host, self.ws_port)
        await site.start()

        logger.info(
            "HTTP+WebSocket server listening on http://%s:%d (WS at /ws)",
            self.ws_host, self.ws_port,
        )
        logger.info("Using fast ADB screencap method (works with all devices)")
        logger.info("Target: %d fps, resolution: %s", self.target_fps, self.max_size)

        self._runner = runner
        await self._frame_producer()

    def stop(self):
        """Stop frame producer."""
        self._running = False
