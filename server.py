"""
Entry-point for the USB Stream server.

Usage:
    python server.py [--serial SERIAL] [--port PORT] [--size WxH] [--fps FPS]
                     [--no-tunnel] [--ui-port PORT]

If --serial is omitted the first detected USB device is used.
A cloudflared quick-tunnel is started by default so the stream is reachable
from anywhere — no account or login required.
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


async def serve_ui(ui_port: int):
    """
    Serve the ui/ directory over plain HTTP so the viewer page is
    reachable through the cloudflared tunnel.
    """
    import os
    from http.server import SimpleHTTPRequestHandler
    import socketserver

    ui_dir = os.path.join(os.path.dirname(__file__), "ui")

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=ui_dir, **kw)

        def log_message(self, fmt, *args):
            pass  # silence access logs

    loop = asyncio.get_event_loop()
    server = socketserver.TCPServer(("0.0.0.0", ui_port), Handler)
    server.allow_reuse_address = True
    logger.info("UI HTTP server listening on http://0.0.0.0:%d", ui_port)
    await loop.run_in_executor(None, server.serve_forever)


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

    # ── WebSocket streamer ────────────────────────────────────────────────────
    # Bind WS to 0.0.0.0 when tunnel is active so cloudflared can reach it
    ws_host = "0.0.0.0" if not args.no_tunnel else args.host
    streamer = ScreenStreamer(
        serial   = serial,
        ws_host  = ws_host,
        ws_port  = args.port,
        max_size = args.size,
        bit_rate = args.bitrate,
        fps      = args.fps,
    )

    # ── Cloudflared tunnel ────────────────────────────────────────────────────
    tunnel: CloudflaredTunnel | None = None
    device_label = serial.replace(":", "_")

    if not args.no_tunnel:
        # Tunnel the UI HTTP port so the browser viewer is accessible remotely
        tunnel = CloudflaredTunnel(
            local_port   = args.ui_port,
            device_label = device_label,
        )
        try:
            public_url = await tunnel.start()
            logger.info("")
            logger.info("=" * 60)
            logger.info("  REMOTE ACCESS LINK for device [%s]", serial)
            logger.info("  %s", public_url)
            logger.info("  Share this URL to view the stream from anywhere.")
            logger.info("  The WebSocket connects automatically through the tunnel.")
            logger.info("=" * 60)
            logger.info("")
        except RuntimeError as exc:
            logger.warning("Tunnel failed to start: %s", exc)
            logger.warning("Falling back to local-only mode.")
            tunnel = None
    else:
        logger.info(
            "Tunnel disabled. Local stream at http://localhost:%d", args.ui_port
        )

    # ── Start UI HTTP server + WebSocket streamer concurrently ────────────────
    try:
        await asyncio.gather(
            serve_ui(args.ui_port),
            streamer.start(),
        )
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
    parser.add_argument("--host",      default="127.0.0.1",
                        help="WebSocket bind host (local-only mode)")
    parser.add_argument("--port",      type=int, default=8765,
                        help="WebSocket port (default 8765)")
    parser.add_argument("--ui-port",   type=int, default=8080,
                        help="HTTP port for UI viewer (default 8080)")
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
