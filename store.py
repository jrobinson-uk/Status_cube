import binascii
import hashlib
import json

import machine

import config

SETTINGS_FILE = "settings.json"
FORMAT_VERSION = 1

# Values in config.py that mean "not filled in yet"
PLACEHOLDERS = ("", "your_wifi_ssid", "your_wifi_password", "xoxp-your-token-here")


def is_set(value) -> bool:
    """True if `value` is a real setting rather than an unedited placeholder."""
    return bool(value) and value not in PLACEHOLDERS


def _defaults() -> dict:
    networks = []
    if is_set(config.WIFI_SSID):
        networks.append({"ssid": config.WIFI_SSID, "password": config.WIFI_PASSWORD})

    return {
        "networks": networks,
        "slack_token": config.SLACK_TOKEN,
        "faces": config.FACE_STATUSES,
    }


# --- obfuscation -----------------------------------------------------------
#
# This is deliberately NOT encryption. The key is derived from the chip ID,
# which lives on the same device, so anything the cube can read an attacker
# with a USB cable can also read via the REPL. It stops `settings.json` being
# plaintext to a casual glance or in a backup; it stops nothing else. Real
# protection would need locked-down code execution — see the README.


def _key() -> bytes:
    return hashlib.sha256(machine.unique_id() + b"status-cube-v1").digest()


def _xor(data: bytes) -> bytes:
    key = _key()
    out = bytearray(len(data))
    for i in range(len(data)):
        out[i] = data[i] ^ key[i % len(key)]
    return bytes(out)


def _migrate(saved: dict) -> dict:
    """Fold the old single-network format into the networks list."""
    if "wifi_ssid" in saved and "networks" not in saved:
        ssid = saved.pop("wifi_ssid", "")
        password = saved.pop("wifi_password", "")
        if is_set(ssid):
            saved["networks"] = [{"ssid": ssid, "password": password}]
    return saved


def load() -> dict:
    """
    Settings from flash, falling back to config.py for anything unset.

    config.py seeds the first boot; after that settings.json wins, so the
    web form can change things without editing code on the device.
    """
    saved = {}
    try:
        with open(SETTINGS_FILE, "rb") as f:
            raw = f.read()
        blob = json.loads(raw)
        if isinstance(blob, dict) and "data" in blob:
            saved = json.loads(_xor(binascii.a2b_base64(blob["data"])).decode())
        else:
            # Plain JSON, e.g. hand-edited for recovery. Accept it.
            saved = blob
    except (OSError, ValueError):
        saved = {}

    settings = _defaults()
    settings.update(_migrate(saved))

    # Merge face-by-face so a partial save, or settings written before
    # presence/dnd existed, can't drop a face or lose its defaults.
    faces = {}
    for face, defaults in config.FACE_STATUSES.items():
        entry = dict(defaults)
        entry.update((saved.get("faces") or {}).get(face, {}))
        faces[face] = entry
    settings["faces"] = faces
    settings.setdefault("networks", [])

    # Dropped feature — discard any leftovers from an earlier settings file.
    settings.pop("admin_salt", None)
    settings.pop("admin_hash", None)

    return settings


def save(settings: dict):
    payload = json.dumps(settings).encode()
    blob = {"v": FORMAT_VERSION, "data": binascii.b2a_base64(_xor(payload)).decode().strip()}
    with open(SETTINGS_FILE, "w") as f:
        json.dump(blob, f)


def has_token(settings: dict) -> bool:
    return is_set(settings.get("slack_token"))


def has_networks(settings: dict) -> bool:
    return any(is_set(n.get("ssid")) for n in settings.get("networks", []))
