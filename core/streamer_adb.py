"""
ADB screencap streamer — captures frames via ADB and converts in-memory with Pillow.
No ffmpeg subprocess needed per frame, significantly faster than the old pipeline.
"""
import asyncio
import subprocess
import logging
import io
from typing import Optional, Dict, Set

from PIL import Image

logger = logging.getLogger("streamer")


def get_device_resolution(serial: str) -> tuple[int, int]:
    """Query the actual device screen resolution via ADB."""
    try:
        result = subprocess.run(
            ["adb", "-s", serial, "shell", "wm", "size"],
            capture_output=True, text=True, timeout=3
        )
        # Output like: "Physical size: 1080x2400" or "Override size: 720x1280"
        output = result.stdout.strip()
        # Prefer override size if present, otherwise physical
        for line in reversed(output.split('\n')):
            if 'size:' in line.lower():
                size_str = line.split(':')[-1].strip()
                w, h = size_str.split('x')
                return int(w), int(h)
    except Exception as e:
        logger.warning("Could not detect device resolution: %s", e)
    
    return 1080, 1920  # fallback


async def adb_screencap_producer(
    serial: str,
    target_fps: int,
    max_size: str,
    running_flag: dict,
    clients: Set,
    last_frame_holder: dict,
):
    """
    Continuously capture frames via ADB screencap and broadcast to clients.
    Uses Pillow for in-memory PNG→JPEG conversion (no ffmpeg subprocess).
    """
    loop = asyncio.get_event_loop()
    frame_count = 0
    frame_delay = 1.0 / min(target_fps, 15)  # Cap at 15fps for ADB method
    
    # Parse target width
    target_width = 640  # Lower default for speed
    if 'x' in max_size:
        try:
            target_width = int(max_size.split('x')[0])
        except ValueError:
            pass
    # Cap width for ADB screencap performance
    target_width = min(target_width, 720)
    
    # Detect device resolution
    dev_w, dev_h = get_device_resolution(serial)
    logger.info("[%s] Device resolution: %dx%d", serial, dev_w, dev_h)
    last_frame_holder['device_width'] = dev_w
    last_frame_holder['device_height'] = dev_h
    
    logger.info("[%s] ADB screencap → Pillow pipeline (no ffmpeg needed)", serial)
    logger.info("Target: %d fps (capped), width: %dpx, JPEG q=50", min(target_fps, 15), target_width)

    def capture_frame() -> Optional[bytes]:
        """Capture single frame via ADB screencap, convert with Pillow."""
        try:
            # Capture PNG via ADB
            p = subprocess.run(
                ["adb", "-s", serial, "exec-out", "screencap", "-p"],
                capture_output=True,
                timeout=3
            )
            if not p.stdout or len(p.stdout) < 100:
                return None

            # Decode PNG and convert to JPEG in-memory with Pillow
            img = Image.open(io.BytesIO(p.stdout))
            
            # Resize for bandwidth
            w, h = img.size
            if w > target_width:
                new_h = int(h * target_width / w)
                img = img.resize((target_width, new_h), Image.NEAREST)
            
            # Encode to JPEG (quality 50 for speed, no EXIF)
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=50, optimize=False)
            return buf.getvalue()
            
        except Exception as e:
            logger.debug("Frame capture error: %s", e)
            return None

    consecutive_failures = 0
    
    while running_flag.get('running', False):
        frame_start = loop.time()
        
        # Capture frame in thread pool
        frame = await loop.run_in_executor(None, capture_frame)
        
        if frame:
            consecutive_failures = 0
            frame_count += 1
            last_frame_holder['frame'] = frame

            if frame_count == 1:
                logger.info("✓ First frame: %d bytes", len(frame))
            elif frame_count % 150 == 0:
                elapsed = loop.time() - frame_start
                logger.info("Frame %d (capture: %.0fms)", frame_count, elapsed * 1000)

            # Broadcast to all connected clients
            if clients:
                dead = set()
                for ws in list(clients):
                    try:
                        await ws.send_bytes(frame)
                    except Exception:
                        dead.add(ws)
                clients -= dead
        else:
            consecutive_failures += 1
            if consecutive_failures >= 10:
                logger.warning("10 consecutive capture failures — check USB connection")
                consecutive_failures = 0
        
        # Maintain target FPS
        frame_time = loop.time() - frame_start
        sleep_time = max(0.01, frame_delay - frame_time)
        await asyncio.sleep(sleep_time)
    
    logger.info("ADB screencap producer stopped after %d frames", frame_count)
