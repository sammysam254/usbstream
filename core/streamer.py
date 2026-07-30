"""
Screen streamer — captures live frames from Android device via scrcpy,
encodes to JPEG, strips EXIF, and broadcasts over WebSocket with bidirectional control.

Uses scrcpy --record=- (H.264 to stdout) for fastest possible streaming performance.
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

        self._clients: Set[web.WebSocketResponse] = set()
        self._running  = False
        self._last_frame: Optional[bytes] = None
        self._scrcpy_proc: Optional[subprocess.Popen] = None
        self._ffmpeg_proc: Optional[subprocess.Popen] = None

        # Path to the UI static files
        self._ui_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui")

    # ── scrcpy raw stream capture ─────────────────────────────────────────────

    def _start_scrcpy(self) -> subprocess.Popen:
        """
        Launch scrcpy to output H.264 stream to stdout.
        Uses --record=- to pipe video to stdout for FFmpeg processing.
        Compatible with scrcpy 4.x
        """
        size_num = self.max_size.split('x')[0]
        cmd = [
            "scrcpy",
            "-s", self.serial,
            "--video-codec=h264",
            f"--max-size={size_num}",
            f"--video-bit-rate={self.bit_rate}",
            f"--max-fps={self.fps}",
            "--no-audio",
            "--video-source=display",    # scrcpy 4.x way to specify display source
            "--record=-",                # Output to stdout
            "--record-format=h264",      # Raw H.264 format
            "--no-window",               # Don't show scrcpy window (4.x replacement for --no-display)
        ]
        logger.info("Starting scrcpy: %s", " ".join(cmd))
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,      # Capture errors for debugging
        )

    def _start_ffmpeg(self, h264_input) -> subprocess.Popen:
        """
        Convert scrcpy's H.264 stream to MJPEG frames for WebSocket transmission.
        """
        cmd = [
            "ffmpeg",
            "-loglevel", "quiet",
            "-f", "h264",
            "-i", "pipe:0",
            "-f", "mjpeg",
            "-q:v", "3",
            "pipe:1",
        ]
        return subprocess.Popen(
            cmd,
            stdin=h264_input,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    # ── MJPEG frame producer loop ─────────────────────────────────────────────

    async def _frame_producer(self):
        """
        Read MJPEG frames from FFmpeg, strip EXIF, cache latest frame,
        and broadcast to all connected WebSocket clients.
        """
        loop = asyncio.get_event_loop()
        ffmpeg = self._ffmpeg_proc

        SOI = b"\xff\xd8"  # JPEG Start Of Image
        EOI = b"\xff\xd9"  # JPEG End Of Image
        buf = b""

        logger.info("[%s] Frame producer started (scrcpy raw stream)", self.serial)

        while self._running:
            try:
                chunk = await loop.run_in_executor(None, ffmpeg.stdout.read, 65536)
            except Exception as e:
                logger.error("Frame read error: %s", e)
                break

            if not chunk:
                await asyncio.sleep(0.01)
                continue

            buf += chunk

            # Extract complete JPEG frames from buffer
            while True:
                start = buf.find(SOI)
                if start == -1:
                    buf = b""
                    break

                end = buf.find(EOI, start + 2)
                if end == -1:
                    buf = buf[start:]  # Keep partial frame
                    break

                frame = buf[start: end + 2]
                buf = buf[end + 2:]

                # Strip EXIF/GPS metadata for privacy
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
                x = int(event.get("x", 0))
                y = int(event.get("y", 0))
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
        except Exception as e:
            logger.error("Control event processing error: %s", e)

    # ── aiohttp handlers ──────────────────────────────────────────────────────

    async def _index_handler(self, request: web.Request) -> web.FileResponse:
        """Serve the UI index.html."""
        return web.FileResponse(os.path.join(self._ui_dir, "index.html"))

    # ── Public API ────────────────────────────────────────────────────────────

    def _reset_adb_connection(self):
        """
        Reset ADB to prevent stuck daemon issues (80% of connection failures).
        Kills server and restarts to ensure clean connection.
        """
        logger.info("Resetting ADB connection...")
        try:
            # Kill any hung ADB instances
            subprocess.run(["adb", "kill-server"], capture_output=True, timeout=5)
            # Restart and verify device
            subprocess.run(["adb", "start-server"], capture_output=True, timeout=5)
            result = subprocess.run(["adb", "devices"], capture_output=True, timeout=5, text=True)
            logger.info("ADB devices after reset:\n%s", result.stdout)
        except Exception as e:
            logger.warning("ADB reset failed: %s", e)

    async def start(self):
        """Start scrcpy, ffmpeg, aiohttp server, and frame producer."""
        self._running = True

        # Reset ADB connection first to prevent stuck daemon issues
        self._reset_adb_connection()

        # Start scrcpy H.264 stream to stdout
        self._scrcpy_proc = self._start_scrcpy()
        await asyncio.sleep(2.0)  # Give scrcpy time to negotiate with device
        
        # Check if scrcpy is running
        if self._scrcpy_proc.poll() is not None:
            stderr_output = self._scrcpy_proc.stderr.read().decode('utf-8', errors='ignore')
            logger.error("scrcpy failed to start. Error output:")
            logger.error(stderr_output)
            raise RuntimeError(f"scrcpy process exited immediately: {stderr_output[:200]}")

        # Start FFmpeg to convert H.264 → MJPEG
        self._ffmpeg_proc = self._start_ffmpeg(self._scrcpy_proc.stdout)

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
        logger.info("Using scrcpy --record=- (H.264 to stdout)")
        logger.info("Frame settings: %s @ %d fps, bitrate %s", self.max_size, self.fps, self.bit_rate)

        self._runner = runner
        await self._frame_producer()

    def stop(self):
        """Stop all streaming processes."""
        self._running = False
        for proc in (self._ffmpeg_proc, self._scrcpy_proc):
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    pass
