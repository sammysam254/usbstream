"""
ADB device manager — detects USB-connected devices and manages ADB connections.
"""
import subprocess
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Device:
    serial: str
    model: str
    status: str


def _run(cmd: List[str]) -> str:
    """Run a command and return stdout, silently returning empty string on error."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout.strip()
    except Exception:
        return ""


def list_devices() -> List[Device]:
    """Return all currently connected ADB devices."""
    output = _run(["adb", "devices", "-l"])
    devices = []
    for line in output.splitlines()[1:]:
        line = line.strip()
        if not line or "offline" in line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial = parts[0]
        status = parts[1]
        model_match = re.search(r"model:(\S+)", line)
        model = model_match.group(1) if model_match else "unknown"
        devices.append(Device(serial=serial, model=model, status=status))
    return devices


def get_device_prop(serial: str, prop: str) -> str:
    """Read a single Android system property from a device."""
    return _run(["adb", "-s", serial, "shell", "getprop", prop])


def set_device_prop(serial: str, prop: str, value: str) -> bool:
    """
    Attempt to set an Android system property (requires root or writable prop).
    Returns True if the command succeeded.
    """
    result = subprocess.run(
        ["adb", "-s", serial, "shell", "setprop", prop, value],
        capture_output=True, text=True, timeout=10
    )
    return result.returncode == 0


def revoke_location_permission(serial: str, package: str = "") -> None:
    """
    Revoke fine and coarse location permissions from a package,
    or from all non-system packages if no package specified.
    """
    if package:
        packages = [package]
    else:
        out = _run(["adb", "-s", serial, "shell",
                    "pm", "list", "packages", "-3"])
        packages = [ln.replace("package:", "").strip()
                    for ln in out.splitlines() if ln.strip()]

    for pkg in packages:
        for perm in [
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.ACCESS_COARSE_LOCATION",
            "android.permission.ACCESS_BACKGROUND_LOCATION",
        ]:
            subprocess.run(
                ["adb", "-s", serial, "shell",
                 "pm", "revoke", pkg, perm],
                capture_output=True, timeout=10
            )


def disable_gps(serial: str) -> None:
    """Disable GPS/location providers via settings commands."""
    cmds = [
        ["adb", "-s", serial, "shell",
         "settings", "put", "secure", "location_mode", "0"],
        ["adb", "-s", serial, "shell",
         "settings", "put", "secure", "location_providers_allowed", ""],
    ]
    for cmd in cmds:
        subprocess.run(cmd, capture_output=True, timeout=10)
