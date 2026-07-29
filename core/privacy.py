"""
Privacy layer — strips device fingerprint identifiers and location metadata.
Operates via ADB shell commands; does NOT require root for most operations.
"""
import subprocess
import uuid
import random
import string
from typing import Dict
from .adb_manager import get_device_prop, set_device_prop, disable_gps


# Properties that identify a device fingerprint
FINGERPRINT_PROPS = [
    "ro.product.model",
    "ro.product.brand",
    "ro.product.name",
    "ro.product.manufacturer",
    "ro.product.device",
    "ro.build.fingerprint",
    "ro.build.id",
    "ro.build.display.id",
    "ro.serialno",
    "ro.boot.serialno",
    "persist.sys.timezone",
]


def collect_fingerprint(serial: str) -> Dict[str, str]:
    """Read the current device fingerprint properties."""
    return {prop: get_device_prop(serial, prop) for prop in FINGERPRINT_PROPS}


def _random_string(length: int = 8) -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def _fake_serial() -> str:
    return ''.join(random.choices(string.hexdigits[:16], k=16)).upper()


def apply_privacy_overrides(serial: str) -> Dict[str, str]:
    """
    Attempt to overwrite identifying build props with randomised values.
    Works reliably only on rooted devices or emulators; on stock devices
    the props are read-only but the attempt is still made.
    Returns a dict of { prop: new_value } for what was applied.
    """
    overrides = {
        "ro.product.model":       f"Generic-{_random_string(4)}",
        "ro.product.brand":       "AOSP",
        "ro.product.name":        f"device_{_random_string(4)}",
        "ro.product.manufacturer":"Generic",
        "ro.product.device":      f"dev_{_random_string(4)}",
        "ro.build.fingerprint":   (
            f"AOSP/generic/{_random_string(4)}:"
            f"13/TQ3A.230805.001/{_random_string(7)}:user/release-keys"
        ),
        "ro.build.id":            f"TQ3A.{_random_string(6)}",
        "ro.serialno":            _fake_serial(),
        "ro.boot.serialno":       _fake_serial(),
    }
    applied = {}
    for prop, value in overrides.items():
        if set_device_prop(serial, prop, value):
            applied[prop] = value
    return applied


def strip_location_services(serial: str) -> None:
    """Disable all location services on the device."""
    disable_gps(serial)


def strip_exif_from_frame(frame_bytes: bytes) -> bytes:
    """
    Remove EXIF metadata (including GPS tags) from a JPEG frame.
    Scans for APP1 (0xFFE1) EXIF markers and removes the segment.
    """
    if not frame_bytes:
        return frame_bytes

    # JPEG starts with FFD8; we walk markers to strip APP1 EXIF
    out = bytearray()
    i = 0
    data = frame_bytes

    if len(data) < 4 or data[0] != 0xFF or data[1] != 0xD8:
        # Not a JPEG, return as-is
        return frame_bytes

    # Write SOI
    out.extend(data[0:2])
    i = 2

    while i < len(data) - 1:
        if data[i] != 0xFF:
            # Raw image data / not a marker — copy remainder
            out.extend(data[i:])
            break

        marker = data[i + 1]

        # SOI / EOI markers have no length field
        if marker in (0xD8, 0xD9):
            out.extend(data[i:i + 2])
            i += 2
            continue

        if i + 3 >= len(data):
            out.extend(data[i:])
            break

        seg_len = (data[i + 2] << 8) | data[i + 3]
        seg_end = i + 2 + seg_len

        # APP1 (0xE1) with EXIF header — skip this segment
        if marker == 0xE1 and data[i + 4:i + 10] == b"Exif\x00\x00":
            i = seg_end
            continue

        # Keep all other segments
        out.extend(data[i:seg_end])
        i = seg_end

    return bytes(out)
