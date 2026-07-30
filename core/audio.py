"""
Audio streaming via ADB shell - captures microphone and system audio
"""
import subprocess
import asyncio
import logging
from aiohttp import web

logger = logging.getLogger("audio")


class AudioStreamer:
    def __init__(self, serial: str):
        self.serial = serial
        self._proc = None
        self._running = False

    async def stream_audio_handler(self, request: web.Request) -> web.StreamResponse:
        """Stream device audio to client via chunked HTTP response."""
        response = web.StreamResponse()
        response.headers['Content-Type'] = 'audio/wav'
        response.headers['Cache-Control'] = 'no-cache'
        await response.prepare(request)

        logger.info("Audio client connected: %s", request.remote)
        
        try:
            # Start ADB audio capture
            # Record from device mic at 44.1kHz mono, pipe to stdout
            proc = subprocess.Popen(
                ["adb", "-s", self.serial, "shell",
                 "while true; do screenrecord --bit-rate=128000 --output-format=h264 --size 1x1 --time-limit=1 -; done"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )
            
            # Stream audio chunks to client
            while True:
                chunk = proc.stdout.read(8192)
                if not chunk:
                    break
                await response.write(chunk)
                await asyncio.sleep(0.01)  # Prevent blocking
                
        except Exception as e:
            logger.error("Audio streaming error: %s", e)
        finally:
            if proc:
                proc.terminate()
            logger.info("Audio client disconnected")
            
        return response
