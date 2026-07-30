"""
Screen streamer — captures live frames from Android device via scrcpy video stream,
encodes to JPEG, strips EXIF, and broadcasts over WebSocket with bidirectional control.

Uses scrcpy for high-performance streaming optimized for MediaTek/entry-level hardware.
Served via aiohttp on a single unified port (HTTP UI at / and WS at /ws).
"""
import asyncio
import subprocess
import logging
import os
import json
import re
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

    # ── scrcpy + FFmpeg video stream ─────────────────────────────────────────

    async def _frame_producer(self):
        """
        Use ADB screencap method for reliable streaming on all devices.
        Falls back from scrcpy due to MediaTek hardware encoder limitations.
        """
        from .streamer_adb import adb_screencap_producer
        
        # Pre-flight check: wake device and ensure stable connection
        logger.info("[%s] Pre-flight check: waking device and testing connection", self.serial)
        try:
            # Wake device
            subprocess.run(
                ["adb", "-s", self.serial, "shell", "input", "keyevent", "KEYCODE_WAKEUP"],
                capture_output=True,
                timeout=3
            )
            await asyncio.sleep(1)
            
            # Test connection
            result = subprocess.run(
                ["adb", "-s", self.serial, "shell", "echo", "test"],
                capture_output=True,
                timeout=3
            )
            if result.returncode != 0:
                logger.error("Device connection test failed - check USB connection")
                self._running = False
                return
            logger.info("Device connection stable")
        except Exception as e:
            logger.error("Pre-flight check failed: %s", e)
            self._running = False
            return
        
        logger.info("HTTP+WebSocket server listening on http://%s:%d (WS at /ws)", 
                   self.ws_host, self.ws_port)
        
        # Use ADB screencap producer
        running_flag = {'running': self._running}
        last_frame_holder = {'frame': None}
        
        await adb_screencap_producer(
            self.serial,
            self.target_fps,
            self.max_size,
            running_flag,
            self._clients,
            last_frame_holder
        )
        
        self._last_frame = last_frame_holder['frame']
                        continue
                    
                    no_data_count = 0
                    buffer += chunk
                    
                    # Find JPEG markers (SOI: 0xFFD8, EOI: 0xFFD9)
                    while True:
                        start = buffer.find(b'\xff\xd8')
                        if start == -1:
                            buffer = buffer[-2:]  # Keep last 2 bytes for next search
                            break
                        
                        end = buffer.find(b'\xff\xd9', start + 2)
                        if end == -1:
                            # Incomplete frame, wait for more data
                            break
                        
                        # Extract complete JPEG frame
                        frame = buffer[start:end + 2]
                        buffer = buffer[end + 2:]
                        
                        # Strip EXIF and broadcast
                        frame_clean = strip_exif_from_frame(frame)
                        frame_count += 1
                        self._last_frame = frame_clean
                        
                        if frame_count == 1:
                            logger.info("First frame captured: %d bytes", len(frame_clean))
                        elif frame_count % 300 == 0:
                            logger.info("Frame %d: streaming from scrcpy", frame_count)
                        
                        # Broadcast to clients
                        if self._clients:
                            dead = set()
                            for ws in list(self._clients):
                                try:
                                    await ws.send_bytes(frame_clean)
                                except Exception:
                                    dead.add(ws)
                            self._clients -= dead
                
                except Exception as e:
                    logger.error("Frame processing error: %s", e)
                    await asyncio.sleep(0.1)
            
            # Cleanup
            ffmpeg_proc.terminate()
            scrcpy_proc.terminate()
            try:
                ffmpeg_proc.wait(timeout=2)
                scrcpy_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                ffmpeg_proc.kill()
                scrcpy_proc.kill()
            
            logger.info("Frame producer stopped")
            
        except FileNotFoundError:
            logger.error("scrcpy not found - please install scrcpy")
            self._running = False
        except Exception as e:
            logger.error("Frame producer error: %s", e)
            self._running = False

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
        """Start aiohttp server and scrcpy frame producer."""
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

        self._runner = runner
        await self._frame_producer()

    def stop(self):
        """Stop frame producer."""
        self._running = False
