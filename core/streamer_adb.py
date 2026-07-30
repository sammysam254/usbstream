"""
ADB screencap streamer — captures frames via ADB and converts in-memory with Pillow.
Uses raw RGBA framebuffer dumping for ultra-fast frame rates (50-100ms per frame),
falling back to PNG screencap if raw capture is unsupported by the device.
"""
import asyncio
import io
import logging
import subprocess
import struct
from typing import Optional, Set

from PIL import Image

logger = logging.getLogger("streamer")


def get_device_resolution(serial: str) -> tuple[int, int]:
    """Query the actual device screen resolution via ADB."""
    try:
        result = subprocess.run(
            ["adb", "-s", serial, "shell", "wm", "size"],
            capture_output=True, text=True, timeout=3
        )
        output = result.stdout.strip()
        for line in reversed(output.split('\n')):
            if 'size:' in line.lower():
                size_str = line.split(':')[-1].strip()
                w, h = size_str.split('x')
                return int(w), int(h)
    except Exception as e:
        logger.warning("Could not detect device resolution: %s", e)
    
    return 1080, 1920  # fallback


def capture_raw_screencap(serial: str, timeout: float = 5.0) -> Optional[Image.Image]:
    """
    Capture raw uncompressed framebuffer via ADB exec-out screencap.
    Bypasses PNG compression on device CPU for maximum performance (50-100ms).
    """
    try:
        p = subprocess.run(
            ["adb", "-s", serial, "exec-out", "screencap"],
            capture_output=True,
            timeout=timeout
        )
        data = p.stdout
        if not data or len(data) < 16:
            return None

        # Parse 16-byte Android screencap header (width, height, format, color space)
        w, h, fmt, _ = struct.unpack('<IIII', data[:16])
        if w <= 0 or h <= 0 or w > 8000 or h > 8000:
            return None

        # Determine expected bytes based on pixel format
        # Formats: 1: RGBA_8888, 2: RGBX_8888, 3: RGB_888, 4: RGB_565, 5: BGRA_8888
        expected_4bpp = 16 + w * h * 4
        if len(data) >= expected_4bpp:
            pixel_bytes = data[16:expected_4bpp]
            if fmt == 5:  # BGRA
                return Image.frombytes('RGBA', (w, h), pixel_bytes, 'raw', 'BGRA')
            else:         # RGBA / RGBX
                return Image.frombytes('RGBA', (w, h), pixel_bytes, 'raw', 'RGBA')

        expected_3bpp = 16 + w * h * 3
        if len(data) >= expected_3bpp and fmt == 3:
            return Image.frombytes('RGB', (w, h), data[16:expected_3bpp], 'raw', 'RGB')

        expected_2bpp = 16 + w * h * 2
        if len(data) >= expected_2bpp and fmt == 4:
            return Image.frombytes('RGB', (w, h), data[16:expected_2bpp], 'raw', 'BGR;16')

    except Exception as e:
        logger.debug("Raw screencap error: %s", e)

    return None


def capture_png_screencap(serial: str, timeout: float = 8.0) -> Optional[Image.Image]:
    """Capture single PNG frame via ADB screencap -p (fallback method)."""
    try:
        p = subprocess.run(
            ["adb", "-s", serial, "exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=timeout
        )
        if not p.stdout or len(p.stdout) < 100:
            return None
        return Image.open(io.BytesIO(p.stdout))
    except Exception as e:
        logger.debug("PNG screencap error: %s", e)
        return None


async def adb_screencap_producer(
    serial: str,
    target_fps: int,
    max_size: str,
    running_flag: dict,
    clients: Set,
    last_frame_holder: dict,
):
    """
    Continuously capture frames via ADB and broadcast to WebSocket clients.
    Uses high-speed raw RGBA capture with PNG fallback.
    """
    loop = asyncio.get_event_loop()
    frame_count = 0
    frame_delay = 1.0 / min(target_fps, 25)
    
    # Parse target width
    target_width = 720
    if 'x' in max_size:
        try:
            target_width = int(max_size.split('x')[0])
        except ValueError:
            pass
    target_width = min(target_width, 720)
    
    dev_w, dev_h = get_device_resolution(serial)
    logger.info("[%s] Device resolution: %dx%d", serial, dev_w, dev_h)
    last_frame_holder['device_width'] = dev_w
    last_frame_holder['device_height'] = dev_h
    
    logger.info("[%s] Starting ADB capture pipeline (raw RGBA + Pillow)", serial)
    logger.info("Target: %d fps, width: %dpx, JPEG q=50", min(target_fps, 25), target_width)

    use_raw = True

    def capture_frame() -> Optional[bytes]:
        nonlocal use_raw
        img: Optional[Image.Image] = None

        if use_raw:
            img = capture_raw_screencap(serial, timeout=5.0)
            if img is None:
                logger.info("[%s] Raw screencap unavailable/failed, switching to PNG capture fallback", serial)
                use_raw = False
                img = capture_png_screencap(serial, timeout=8.0)
        else:
            img = capture_png_screencap(serial, timeout=8.0)
            if img is None:
                # Retest raw screencap
                img = capture_raw_screencap(serial, timeout=5.0)
                if img is not None:
                    use_raw = True

        if img is None:
            return None

        try:
            w, h = img.size
            if w > target_width:
                new_h = int(h * target_width / w)
                img = img.resize((target_width, new_h), Image.NEAREST)
            
            buf = io.BytesIO()
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(buf, format='JPEG', quality=50, optimize=False)
            return buf.getvalue()
        except Exception as e:
            logger.debug("Frame processing error: %s", e)
            return None

    consecutive_failures = 0
    
    while running_flag.get('running', False):
        frame_start = loop.time()
        
        frame = await loop.run_in_executor(None, capture_frame)
        
        if frame:
            consecutive_failures = 0
            frame_count += 1
            last_frame_holder['frame'] = frame

            if frame_count == 1:
                logger.info("✓ First frame captured successfully (%d bytes)", len(frame))
            elif frame_count % 150 == 0:
                elapsed = loop.time() - frame_start
                logger.info("Frame %d (capture: %.0fms)", frame_count, elapsed * 1000)

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
                logger.warning("[%s] 10 consecutive capture failures — attempting ADB reconnect recovery...", serial)
                try:
                    subprocess.run(["adb", "-s", serial, "reconnect"], capture_output=True, timeout=5)
                except Exception:
                    pass
                consecutive_failures = 0
        
        frame_time = loop.time() - frame_start
        sleep_time = max(0.01, frame_delay - frame_time)
        await asyncio.sleep(sleep_time)
    
    logger.info("ADB screencap producer stopped after %d frames", frame_count)

