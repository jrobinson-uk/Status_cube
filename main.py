import time
from machine import I2C, Pin

import bootsel
import config
import gesture
import slack
import store
import web
import wifi
from mpu9250 import MPU9250


def detect_face(ax, ay, az):
    """Return face key ("z+", "x-", ...), or None if orientation is ambiguous."""
    candidates = [
        ("x+", ax), ("x-", -ax),
        ("y+", ay), ("y-", -ay),
        ("z+", az), ("z-", -az),
    ]
    best_axis, best_val = max(candidates, key=lambda c: c[1])
    if best_val >= config.GRAVITY_THRESHOLD:
        return best_axis
    return None


def status_led():
    """Onboard LED — "LED" on the Pico W, GP25 on the original Pico."""
    try:
        return Pin("LED", Pin.OUT)
    except (TypeError, ValueError):
        try:
            return Pin(25, Pin.OUT)
        except Exception:
            return None


def blink(led, times: int = 2, ms: int = 120):
    """Acknowledge a gesture. Replace with the RGB indicator once it's wired."""
    if led is None:
        return
    for _ in range(times):
        led.on()
        time.sleep_ms(ms)
        led.off()
        time.sleep_ms(ms)


def go_online(settings) -> bool:
    """
    Join the best saved network, falling back to setup AP mode.

    Returns True if we reached the internet. Config mode is entered when
    there's nothing saved, nothing reachable, or BOOTSEL is held at boot.
    """
    if bootsel.held_at_boot():
        print("BOOTSEL held — starting in setup mode.")
    elif not store.has_networks(settings):
        print("No WiFi configured.")
    elif wifi.connect_best(settings["networks"]):
        return True
    else:
        print("No saved network reachable.")

    wifi.start_ap()
    return False


def apply_status(settings, face) -> bool:
    """Push status, presence and notification state. False if nothing went out."""
    entry = settings["faces"][face]
    text = entry["status_text"]
    presence = entry.get("presence", "auto")
    muted = bool(entry.get("dnd", False))

    print(f"Face {face} -> {text} [{presence}]" + (" muted" if muted else ""))

    if not store.has_token(settings):
        print("  no Slack token set — visit the config page")
        return False

    if not wifi.is_connected():
        print("  not on WiFi, skipping")
        return False

    token = settings["slack_token"]

    # Status is the gate: presence and DND need extra scopes, so a failure
    # there shouldn't make us retry the whole face on every loop.
    sent = slack.set_status(token, text, entry["status_emoji"])
    slack.set_presence(token, presence)

    if muted:
        slack.snooze(token, config.DND_SNOOZE_MINUTES)
    else:
        slack.end_snooze(token)

    return sent


def run():
    settings = store.load()
    online = go_online(settings)
    ap_open = not online

    server = web.start()
    print(f"Config page: http://{wifi.current_ip()}/")

    i2c = I2C(
        config.I2C_BUS,
        sda=Pin(config.I2C_SDA_PIN),
        scl=Pin(config.I2C_SCL_PIN),
        freq=config.I2C_FREQ,
    )
    imu = MPU9250(i2c)
    print(f"MPU9250 ready (WHO_AM_I: 0x{imu.whoami():02X})")
    print("Monitoring cube face...\n")

    led = status_led()
    debounce_ms = int(config.DEBOUNCE_SECONDS * 1000)
    shaker = gesture.ShakeDetector(
        config.SHAKE_THRESHOLD_G,
        config.SHAKE_COUNT,
        int(config.SHAKE_WINDOW_SECONDS * 1000),
    )

    # `pending` is the face currently being held; `reported` is the last one
    # actually sent to Slack. A face must be held for the full debounce
    # window before it counts — mid-roll the cube passes through orientations
    # that briefly exceed the threshold.
    reported = None
    pending = None
    pending_since = time.ticks_ms()

    while True:
        ax, ay, az = imu.read_accel()

        # Shake to open the setup network, shake again to close it. While
        # offline the AP is the only way in, so it stays up regardless.
        if shaker.update(ax, ay, az):
            if ap_open and online:
                wifi.stop_ap()
                ap_open = False
                print("\nSetup network closed.\n")
                blink(led, times=1)
            elif not ap_open:
                print("\nShake detected — opening setup network.")
                wifi.start_ap()
                ap_open = True
                print(f"Config page: http://{wifi.current_ip()}/\n")
                blink(led, times=3)
            # A shake is a deliberate handling event; don't let the tumbling
            # that produced it count towards a face change.
            pending = None
            pending_since = time.ticks_ms()

        if web.poll(server, settings, not online):
            # Face labels may have changed under us; re-send on next settle.
            reported = None

        face = detect_face(ax, ay, az)

        if face != pending:
            pending = face
            pending_since = time.ticks_ms()
        elif face != reported and time.ticks_diff(time.ticks_ms(), pending_since) >= debounce_ms:
            if face is None:
                print("Face up: (ambiguous — cube is tilted)")
                reported = None
            elif apply_status(settings, face):
                reported = face
            elif not online:
                # In setup mode there's no internet; log it and move on
                # rather than retrying every loop.
                reported = face

        time.sleep_ms(50)


run()
