"""
Cloudflare Tunnel manager.

Spawns a `cloudflared tunnel --url` quick-tunnel that exposes the local
WebSocket + HTTP port to a public trycloudflare.com URL.

No Cloudflare account or login needed — uses the free quick-tunnel service.
Each call to start() gives a fresh randomly-assigned URL valid for the
lifetime of the process.
"""
import asyncio
import logging
import re
import subprocess
from typing import Optional

logger = logging.getLogger("tunnel")

# Regex to extract the assigned public URL from cloudflared output
_URL_RE = re.compile(r"https://[a-z0-9\-]+\.trycloudflare\.com", re.IGNORECASE)


class CloudflaredTunnel:
    def __init__(self, local_port: int, device_label: str = "device"):
        self.local_port   = local_port
        self.device_label = device_label
        self.public_url:  Optional[str] = None
        self._proc:       Optional[asyncio.subprocess.Process] = None

    async def start(self) -> str:
        """
        Launch cloudflared and wait until the public URL is printed.
        Returns the public https URL string.
        Raises RuntimeError if the URL is not found within 30 seconds.
        """
        cmd = [
            "cloudflared", "tunnel",
            "--url", f"http://localhost:{self.local_port}",
            "--no-autoupdate",
        ]
        logger.info("[%s] Starting cloudflared tunnel → port %d",
                    self.device_label, self.local_port)

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        url = await self._wait_for_url(timeout=30)
        self.public_url = url

        logger.info(
            "[%s] Tunnel active:\n"
            "  ┌─────────────────────────────────────────────────────\n"
            "  │  Remote access URL: %s\n"
            "  └─────────────────────────────────────────────────────",
            self.device_label, url
        )
        # Kick off background stderr drainer so the pipe doesn't block
        asyncio.ensure_future(self._drain_stderr())
        return url

    async def _wait_for_url(self, timeout: int) -> str:
        """
        Read stderr line-by-line (cloudflared logs to stderr) until we
        see the trycloudflare URL or time out.
        """
        deadline = asyncio.get_event_loop().time() + timeout

        while asyncio.get_event_loop().time() < deadline:
            try:
                line = await asyncio.wait_for(
                    self._proc.stderr.readline(), timeout=2.0
                )
            except asyncio.TimeoutError:
                continue

            if not line:
                break

            text = line.decode(errors="replace").strip()
            logger.debug("[cloudflared] %s", text)

            match = _URL_RE.search(text)
            if match:
                return match.group(0)

        raise RuntimeError(
            f"cloudflared did not produce a tunnel URL within {timeout}s. "
            "Make sure cloudflared is installed and you have internet access."
        )

    async def _drain_stderr(self):
        """Background task — consume remaining stderr so the pipe never fills."""
        try:
            async for line in self._proc.stderr:
                text = line.decode(errors="replace").strip()
                if text:
                    logger.debug("[cloudflared] %s", text)
        except Exception:
            pass

    def stop(self):
        """Terminate the cloudflared process."""
        if self._proc:
            try:
                self._proc.terminate()
                logger.info("[%s] Tunnel stopped.", self.device_label)
            except Exception:
                pass
            self._proc = None
        self.public_url = None
