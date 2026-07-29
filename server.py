"""
Entry-point for the USB Stream server.

Usage:
    python server.py [--serial SERIAL] [--port PORT] [--size WxH] [--fps FPS]
                     [--no-tunnel]

If --serial is omitted the first detected USB device is used.
A cloudflared quick-tunnel is started by default so the stream is reachable
from anywhere — no account or login required.

The HTTP UI and WebSocket stream are served on the SAME port so a single
cloudflared tunnel covers both.  The viewer page auto-connects via
wss://<tunnel-host>/ws  when opened over HTTPS.
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
from core.tunnel import CloudflaredTunnel

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

    # ── Combined HTTP + WebSocket streamer ────────────────────────────────────
    # Both the UI (HTTP) and the live stream (WebSocket at /ws) are served
    # on the same port so one cloudflared tunnel exposes everything.
    ws_host = "0.0.0.0"   # always bind to all interfaces (tunnel needs this)
    streamer = ScreenStreamer(
        serial   = serial,
        ws_host  = ws_host,
        ws_port  = args.port,      # single unified port (default 8080)
        max_size = args.size,
        bit_rate = args.bitrate,
        fps      = args.fps,
    )

    # ── Cloudflared tunnel ────────────────────────────────────────────────────
    tunnel: CloudflaredTunnel | None = None
    device_label = serial.replace(":", "_")

    if not args.no_tunnel:
        tunnel = CloudflaredTunnel(
            local_port   = args.port,   # tunnel the unified port
            device_label = device_label,
        )
        try:
            public_url = await tunnel.start()
            viewer_url = public_url  # UI is served at /
            ws_url     = f"{public_url.replace('https://', 'wss://')}/ws"
            logger.info("")
            logger.info("=" * 60)
            logger.info("  REMOTE ACCESS LINK for device [%s]", serial)
            logger.info("  Viewer : %s", viewer_url)
            logger.info("  WebSocket: %s", ws_url)
            logger.info("  Share the Viewer URL — the stream connects automatically.")
            logger.info("=" * 60)
            logger.info("")
        except RuntimeError as exc:
            logger.warning("Tunnel failed to start: %s", exc)
            logger.warning("Falling back to local-only mode.")
            tunnel = None
    else:
        logger.info(
            "Tunnel disabled. Local viewer at http://localhost:%d", args.port
        )

    # ── Start streamer (blocks until interrupted) ─────────────────────────────
    try:
        await streamer.start()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down...")
        streamer.stop()
        if tunnel:
            tunnel.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="USB Device Screen Streamer")
    parser.add_argument("--serial",    default=None,
                        help="ADB device serial (auto if omitted)")
    parser.add_argument("--port",      type=int, default=8080,
                        help="Unified HTTP+WebSocket port (default 8080)")
    parser.add_argument("--size",      default="1280x720",
                        help="Max resolution e.g. 1280x720")
    parser.add_argument("--bitrate",   default="4M",
                        help="Video bit-rate e.g. 4M")
    parser.add_argument("--fps",       type=int, default=30,
                        help="Max frames per second")
    parser.add_argument("--no-tunnel", action="store_true",
                        help="Disable cloudflared tunnel (local access only)")
    args = parser.parse_args()

    asyncio.run(main(args))
