"""
Entry-point for the USB Stream server.

Usage:
    python server.py [--serial SERIAL] [--port PORT] [--size WxH] [--fps FPS]

If --serial is omitted the first detected USB device is used.
"""
import argparse
import asyncio
import logging
import sys

from core.adb_manager import list_devices
from core.privacy import (
    apply_privacy_overrides,
    strip_location_services,
    collect_fingerprint,
)
from core.streamer import ScreenStreamer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("server")


def pick_device(serial: str | None) -> str:
    devices = list_devices()
    if not devices:
        logger.error("No ADB devices found. Connect a device with USB debugging enabled.")
        sys.exit(1)

    if serial:
        match = next((d for d in devices if d.serial == serial), None)
        if not match:
            logger.error("Device %s not found. Available: %s",
                         serial, [d.serial for d in devices])
            sys.exit(1)
        return serial

    device = devices[0]
    logger.info("Auto-selected device: %s (%s)", device.serial, device.model)
    return device.serial


async def main(args):
    serial = pick_device(args.serial)

    # ── Privacy hardening ─────────────────────────────────────────────────────
    logger.info("Collecting original device fingerprint...")
    original = collect_fingerprint(serial)
    for k, v in original.items():
        logger.info("  %s = %s", k, v)

    logger.info("Stripping location services...")
    strip_location_services(serial)

    logger.info("Applying fingerprint overrides (root required for full effect)...")
    applied = apply_privacy_overrides(serial)
    if applied:
        for k, v in applied.items():
            logger.info("  Overrode %s → %s", k, v)
    else:
        logger.warning(
            "No props were writable (non-rooted device). "
            "EXIF stripping and location disabling still active."
        )

    # ── Start streamer ────────────────────────────────────────────────────────
    streamer = ScreenStreamer(
        serial   = serial,
        ws_host  = args.host,
        ws_port  = args.port,
        max_size = args.size,
        bit_rate = args.bitrate,
        fps      = args.fps,
    )

    logger.info(
        "Stream ready — open http://localhost:%d in your browser "
        "(serve ui/index.html with any static file server)",
        args.port,
    )
    logger.info("WebSocket endpoint: ws://%s:%d", args.host, args.port)

    try:
        await streamer.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        streamer.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="USB Device Screen Streamer")
    parser.add_argument("--serial",  default=None,        help="ADB device serial")
    parser.add_argument("--host",    default="127.0.0.1", help="WebSocket bind host")
    parser.add_argument("--port",    type=int, default=8765, help="WebSocket port")
    parser.add_argument("--size",    default="1280x720",  help="Max resolution e.g. 1280x720")
    parser.add_argument("--bitrate", default="4M",        help="Video bit-rate e.g. 4M")
    parser.add_argument("--fps",     type=int, default=30, help="Max frames per second")
    args = parser.parse_args()

    asyncio.run(main(args))
