# USB Stream — Privacy-First Interactive Device Screen Streamer

Stream and **remotely control** any Android device's screen over USB with automatic privacy protection:
- ✅ GPS / location data stripped (disabled on-device + EXIF removed per frame)
- ✅ Device fingerprints randomized (model, brand, serial, build ID)
- ✅ **Interactive mouse/touch control** - click, swipe, and control the device remotely
- ✅ **Keyboard shortcuts** - Back, Home, App Switch
- ✅ **Cloudflared tunnel** - instant remote access URL with no configuration

---

## Quick Start (Windows)

**You only need ONE file to get started:**

### **[📥 Click Here to Download install.bat](https://github.com/sammysam254/usbstream/releases/download/v1.1.0/install.bat)**

**How to use:**
1. **Click** the download link above (saves `install.bat` directly to your Downloads folder)
2. **Double-click** `install.bat` to run it
3. **Done!** — It will:
   - Download Python, ADB, scrcpy, FFmpeg, cloudflared automatically
   - Clone this repo from GitHub to `%USERPROFILE%\usbstream-tools\usbstream`
   - Start the server
   - Give you a cloudflared URL to access remotely

**That's it!** Open the cloudflared URL in any browser and you'll see your device screen with full touch control.

---

## What You Get

| Feature | Description |
|---------|-------------|
| **Privacy Mode** | Location services disabled, GPS data stripped from every frame |
| **Interactive Control** | Click on the stream to tap, drag to swipe, long-press for menu |
| **Keyboard Shortcuts** | `Esc` = Back, `Home` = Home screen, `F5` = Recent Apps |
| **Remote Access** | Cloudflared tunnel gives you `https://random-words.trycloudflare.com` link |
| **Local Access** | Works on `http://localhost:8080` if you disable tunnel |
| **Zero Config** | No accounts, no API keys, no port forwarding needed |

---

## Requirements

- **Windows 10/11** (64-bit)
- **Android device** with USB Debugging enabled
- **Internet connection** (for initial setup only)

> **Note:** `install.bat` handles ALL dependencies automatically. No manual installation needed.

---

## Manual Installation (Advanced)

If you prefer to install manually or need to run on Linux/Mac:

### 1. Install Dependencies

### 1. Install Dependencies

| Tool | Install |
|------|---------|
| **Python 3.11+** | https://python.org |
| **ADB** (Android Debug Bridge) | https://developer.android.com/tools/adb |
| **FFmpeg** | https://ffmpeg.org/download.html |
| **cloudflared** | https://github.com/cloudflare/cloudflared/releases |

All tools must be on your system `PATH`.

### 2. Clone and Install

```bash
git clone https://github.com/sammysam254/usbstream.git
cd usbstream
pip install -r requirements.txt
```

### 3. Enable USB Debugging

On your Android device:
1. Go to **Settings** → **About Phone**
2. Tap **Build Number** 7 times to enable Developer Mode
3. Go to **Settings** → **Developer Options**
4. Enable **USB Debugging**
5. Connect device via USB and authorize the computer

### 4. Run

```bash
python server.py
```

The server will:
- Auto-detect your device
- Apply privacy protections
- Start cloudflared tunnel
- Show you the remote access URL

**Open the URL in any browser** - you can now see and control your device!

---

## How to Use

### Touch/Click Controls

| Action | How To |
|--------|--------|
| **Tap** | Click on the screen |
| **Swipe** | Click and drag |
| **Long Press** | Hold mouse button for 500ms → opens menu |
| **Scroll** | Swipe up/down |

### Keyboard Shortcuts

| Key | Android Action |
|-----|----------------|
| `Esc` | Back button |
| `Home` | Home screen |
| `F5` | Recent Apps / Task Switcher |

---

## Server Options

```bash
python server.py [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--serial SERIAL` | auto | ADB device serial (auto-selects first device) |
| `--port PORT` | 8080 | HTTP+WebSocket port |
| `--size WxH` | 1280x720 | Max resolution |
| `--bitrate RATE` | 4M | Video bitrate |
| `--fps FPS` | 30 | Max frames per second |
| `--no-tunnel` | false | Disable cloudflared (local only) |

### Examples

**Two devices - select one:**
```bash
adb devices  # list serials
python server.py --serial R9TN100WXYZ
```

**Low bandwidth:**
```bash
python server.py --size 720x1280 --bitrate 2M --fps 24
```

**Local only (no tunnel):**
```bash
python server.py --no-tunnel
# Access at http://localhost:8080
```

---

## Privacy Protections

| Layer | What It Does |
|-------|-------------|
| **Location disabled** | Sets `location_mode=0` via ADB, clears location providers |
| **Permission revoke** | Revokes `ACCESS_FINE_LOCATION`, `ACCESS_COARSE_LOCATION` from all apps |
| **Fingerprint overrides** | Randomizes `ro.product.*`, `ro.build.fingerprint`, `ro.serialno` (requires root) |
| **Server EXIF strip** | Removes GPS/metadata from each frame before sending |
| **Client EXIF strip** | Browser does second-pass EXIF removal before display |
| **Cloudflared tunnel** | Traffic encrypted via HTTPS/WSS, no exposed ports |

> **Note:** Fingerprint overrides require root and only persist until reboot. Location disabling and EXIF stripping work on all devices.

---

## Architecture

```
Android device (USB)
    └─► ADB screencap (PNG)
            └─► FFmpeg (PNG → JPEG)
                    └─► Python EXIF stripper
                            └─► aiohttp server (HTTP + WebSocket on same port)
                                    ├─► UI served at /
                                    └─► WebSocket at /ws
                                            ├─► Video frames →
                                            └─► ← Touch/key events
                                                    └─► ADB input tap/swipe/keyevent
```

**Unified port design:** Both HTTP (UI) and WebSocket (stream) on port 8080, so one cloudflared tunnel exposes everything.

---

## Troubleshooting

### Device not detected
```bash
adb devices
# If "unauthorized", check device screen for prompt
# If "offline", run: adb kill-server && adb start-server
```

### **Stream drops or freezes after a few minutes**

**USB Power Saving (80% of disconnect issues):**
- **Windows:** Control Panel → Power Options → Change Plan Settings → Advanced → USB Settings → Disable "USB Selective Suspend"
- **Cable Quality:** Use a good quality USB cable and connect directly to motherboard/laptop port (not USB hub)

**ADB Daemon Stuck:**
```bash
adb kill-server
adb start-server
adb devices
```

### **Black screen or stream won't start**

1. **Check scrcpy works standalone:**
```bash
scrcpy -s YOUR_DEVICE_SERIAL --max-size=720
```

2. **Lower resolution/bitrate:**
```bash
python server.py --size 720x1280 --bitrate 2M --fps 20
```

3. **Check FFmpeg is installed:**
```bash
ffmpeg -version
```

### **Mouse clicks not working**

1. **Check logs** - Touch events should show: `Touch tap at (x, y)`
2. **Click directly on device screen** - Not the surrounding black area
3. **Check WebSocket is connected** - Status badge should show "Streaming"

### **Slow/laggy stream**

Lower settings for better performance:
```bash
python server.py --size 720x1280 --bitrate 2M --fps 20
```

### **Cloudflared tunnel fails**

Run locally without tunnel:
```bash
python server.py --no-tunnel
# Access at http://localhost:8080
```

---

## Development

### File Structure

```
usbstream/
├── install.bat           # One-click installer (downloads repo + tools)
├── server.py             # Main entry point
├── requirements.txt      # Python dependencies
├── core/
│   ├── adb_manager.py    # Device detection
│   ├── privacy.py        # Location/fingerprint stripping
│   ├── streamer.py       # Video capture + touch control
│   └── tunnel.py         # Cloudflared tunnel
└── ui/
    └── index.html        # Browser viewer (auto-opens)
```

### Adding Features

**Server-side:** Edit `core/streamer.py` → `_handle_control_event()` to add new ADB commands

**Client-side:** Edit `ui/index.html` → Add event listeners and `sendControl()` calls

---

## License

MIT License - See [LICENSE](LICENSE)

---

## Credits

Built with:
- [scrcpy](https://github.com/Genymobile/scrcpy) - Screen mirroring
- [FFmpeg](https://ffmpeg.org) - Video encoding
- [cloudflared](https://github.com/cloudflare/cloudflared) - Tunneling
- [aiohttp](https://github.com/aio-libs/aiohttp) - Web server

---

## Roadmap

- [ ] Audio streaming (Android audio forwarding via scrcpy 2.0+)
- [ ] Multiple device support (switch between devices in UI)
- [ ] Recording to file
- [ ] Text input from keyboard
- [ ] Clipboard sync
- [ ] File transfer drag-drop
