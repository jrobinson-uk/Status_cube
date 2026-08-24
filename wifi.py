import binascii
import time

import machine
import network

CONNECT_TIMEOUT = 12

# Setup hotspot. The password is derived per-device from the chip ID so a
# room full of cubes doesn't share one hotspot password — it's printed to
# the console on boot.
AP_PREFIX = "StatusCube"
AP_PASSWORD_PREFIX = "cube"

# Used for the DHCP hostname, and for statuscube.local if this firmware
# build includes lwIP's mDNS responder.
HOSTNAME = "statuscube"


def _set_hostname():
    try:
        network.hostname(HOSTNAME)
    except (AttributeError, OSError) as e:
        print("Hostname not supported:", e)


def _uid() -> str:
    return binascii.hexlify(machine.unique_id()).decode()


def ap_credentials() -> tuple:
    uid = _uid()
    return AP_PREFIX + "-" + uid[-4:], AP_PASSWORD_PREFIX + uid[-8:]


def connect(ssid: str, password: str, timeout: int = CONNECT_TIMEOUT):
    """Join one network. Raises RuntimeError if it doesn't associate in time."""
    _set_hostname()
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        return wlan

    print(f"Connecting to {ssid}...")
    wlan.connect(ssid, password)

    deadline = time.ticks_add(time.ticks_ms(), timeout * 1000)
    while not wlan.isconnected():
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            wlan.disconnect()
            raise RuntimeError(f"{ssid}: timed out after {timeout}s")
        time.sleep_ms(200)

    print("Connected:", wlan.ifconfig()[0])
    return wlan


def rank(networks: list) -> list:
    """Saved SSIDs that are currently in range, strongest signal first."""
    known = [n["ssid"] for n in networks if n.get("ssid")]
    if not known:
        return []

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    strongest = {}
    try:
        for entry in wlan.scan():
            ssid = entry[0].decode()
            rssi = entry[3]
            if ssid in known and rssi > strongest.get(ssid, -999):
                strongest[ssid] = rssi
    except Exception as e:
        print("Scan failed:", e)
        return known

    ordered = sorted(strongest.items(), key=lambda kv: kv[1], reverse=True)
    for ssid, rssi in ordered:
        print(f"  {ssid}: {rssi} dBm")

    # Hidden networks never show up in a scan, so try the rest afterwards.
    result = [ssid for ssid, _ in ordered]
    result += [ssid for ssid in known if ssid not in result]
    return result


def connect_best(networks: list, timeout: int = CONNECT_TIMEOUT):
    """Try saved networks strongest-first. Returns the WLAN, or None."""
    passwords = {n["ssid"]: n.get("password", "") for n in networks if n.get("ssid")}
    if not passwords:
        return None

    for ssid in rank(networks):
        try:
            return connect(ssid, passwords.get(ssid, ""), timeout)
        except RuntimeError as e:
            print("  failed:", e)

    return None


def start_ap():
    """Serve our own network so the config page is reachable with no router."""
    ssid, password = ap_credentials()

    _set_hostname()
    ap = network.WLAN(network.AP_IF)

    # A soft reboot leaves the previous AP running with its old settings, and
    # config() on a live interface doesn't reliably take. Cycle it first.
    if ap.active():
        ap.active(False)
        time.sleep_ms(500)

    ap.config(essid=ssid, password=password)
    ap.active(True)

    while not ap.active():
        time.sleep_ms(100)

    print(f"Setup network '{ssid}' (password: {password})")
    print("AP address:", ap.ifconfig()[0])
    return ap


def stop_ap():
    ap = network.WLAN(network.AP_IF)
    if ap.active():
        ap.active(False)


def is_connected() -> bool:
    return network.WLAN(network.STA_IF).isconnected()


def current_ip() -> str:
    """Address the config page is reachable on, station first."""
    sta = network.WLAN(network.STA_IF)
    if sta.active() and sta.isconnected():
        return sta.ifconfig()[0]

    ap = network.WLAN(network.AP_IF)
    if ap.active():
        return ap.ifconfig()[0]

    return "0.0.0.0"
