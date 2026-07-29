# USB Stream — Privacy-First Device Screen Streamer

Stream any Android device's screen over USB with automatic stripping of:
- GPS / location data (disabled on-device + EXIF stripped per frame)
- Device fingerprint fields (model, brand, serial, build fingerprint)

---

## Requirements

| Tool | Install |
|------|---------|
| **Python 3.11+** | https://python.org |
| **ADB** (Android Debug Bridge) | https://developer.android.com/tools/adb |
| **scrcpy** | https://github.com/Genymobile/scrcpy |
| **FFmpeg** | https://ffmpeg.org/download.html |

All four must be on your system `PATH`.

---

## Setup

```bash
pip install -r requirements.txt
```

---

## Running

### 1. Connect your device
Enable **USB Debugging** on the Android device:
Settings → Developer Options → USB Debugging ✓

Plug in via USB, then verify ADB sees it:
```bash
adb devices
```

### 2. Start the server
```bash
python server.py
```

Options:
```
--serial   SERIAL     ADB device serial (auto-selects first device if omitted)
--host     HOST       WebSocket bind address (default: 127.0.0.1)
--port     PORT       WebSocket port        (default: 8765)
--size     WxH        Max resolution        (default: 1280x720)
--bitrate  RATE       Video bitrate         (default: 4M)
--fps      FPS        Max framerate         (default: 30)
```

Example — two devices, pick one, lower bitrate for slow USB:
```bash
python server.py --serial R9TN100WXYZ --size 720x1280 --bitrate 2M --fps 24
```

### 3. Open the viewer

Serve the UI with any static file server, e.g.:
```bash
python -m http.server 8080 --directory ui
```
Then open: **http://localhost:8080**

Enter the WebSocket host/port and click **Connect**.

---

## Privacy protections

| Layer | What it does |
|-------|-------------|
| **Location disabled** | Sets `location_mode=0` and clears `location_providers_allowed` via ADB settings |
| **Permission revoke** | Revokes `ACCESS_FINE_LOCATION`, `ACCESS_COARSE_LOCATION`, `ACCESS_BACKGROUND_LOCATION` from all third-party packages |
| **Fingerprint overrides** | Overwrites `ro.product.*`, `ro.build.fingerprint`, `ro.serialno` with randomised values (requires root for full effect; attempted on all devices) |
| **Server-side EXIF strip** | Each JPEG frame has APP1 EXIF segments removed in Python before being sent over WebSocket |
| **Client-side EXIF strip** | Browser viewer runs a second-pass EXIF strip on every received frame before rendering |
| **Local-only WebSocket** | Server binds to `127.0.0.1` by default — stream never leaves your machine |

> **Note:** Fingerprint prop overrides only persist until reboot and require a rooted device for `ro.*` props.
> On non-rooted devices, location disabling and EXIF stripping are still fully effective.

---

## Architecture

```
Android device (USB)
    └─► scrcpy (raw H.264 to stdout)
            └─► ffmpeg (H.264 → MJPEG frames)
                    └─► Python EXIF stripper
                            └─► WebSocket server (ws://127.0.0.1:8765)
                                    └─► Browser viewer (ui/index.html)
                                            └─► JS EXIF stripper (2nd pass)
                                                    └─► <img> display
```
