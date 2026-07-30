"""
Fallback ADB screencap streamer - reliable method that works on all devices.
"""
import asyncio
import subprocess
import logging
from typing import Optional

from .privacy import strip_exif_from_frame

logger = logging.getLogger("streamer")


async def adb_screencap_producer(serial: str, target_fps: int, max_size: str, running_flag, clients, last_frame_holder):
    """
    Continuously capture frames via ADB screencap and broadcast to clients.
    Reliable method that works with all devices including MediaTek chipsets.
    """
    loop = asyncio.get_event_loop()
    frame_count = 0
    frame_delay = 1.0 / target_fps
    width = max_size.split('x')[0] if 'x' in max_size else "960"
    
    logger.info("[%s] Using ADB screencap method (reliable, works with all devices)", serial)
    logger.info("Target: %d fps, resolution: %sx?", target_fps, width)

    def capture_frame():
        """Capture single frame via ADB screencap and convert to JPEG."""
        try:
            # Capture PNG via ADB
            p1 = subprocess.run(
                ["adb", "-s", serial, "exec-out", "screencap", "-p"],
                capture_output=True,
                timeout=2
            )
            if not p1.stdout or len(p1.stdout) < 100:
                return None

            # Convert PNG to JPEG and resize
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

    while running_flag['running']:
        frame_start = loop.time()
        
        # Capture frame in executor
        frame = await loop.run_in_executor(None, capture_frame)
        
        if frame:
            frame_count += 1
            last_frame_holder['frame'] = frame

            if frame_count == 1:
                logger.info("First frame captured: %d bytes", len(frame))
            elif frame_count % 100 == 0:
                logger.info("Frame %d: streaming at ~%d fps", frame_count, target_fps)

            # Broadcast to all clients
            if clients:
                dead = set()
                for ws in list(clients):
                    try:
                        await ws.send_bytes(frame)
                    except Exception:
                        dead.add(ws)
                clients -= dead
        
        # Maintain target FPS
        frame_time = loop.time() - frame_start
        sleep_time = max(0, frame_delay - frame_time)
        await asyncio.sleep(sleep_time)
    
    logger.info("ADB screencap producer stopped")
