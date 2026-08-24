import time

try:
    import rp2
except ImportError:
    rp2 = None

# Reading BOOTSEL briefly halts execution from flash, so don't poll it on
# every pass of a 50ms loop.
POLL_INTERVAL_MS = 250
HOLD_MS = 2000


def pressed() -> bool:
    if rp2 is None or not hasattr(rp2, "bootsel_button"):
        return False
    return bool(rp2.bootsel_button())


def held_at_boot(window_ms: int = 500) -> bool:
    """True if BOOTSEL is down during startup — the 'boot into config' gesture."""
    deadline = time.ticks_add(time.ticks_ms(), window_ms)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        if pressed():
            return True
        time.sleep_ms(50)
    return False


class Watcher:
    """Throttled long-press detector for the main loop."""

    def __init__(self, hold_ms: int = HOLD_MS, interval_ms: int = POLL_INTERVAL_MS):
        self._hold_ms = hold_ms
        self._interval_ms = interval_ms
        self._last_poll = time.ticks_ms()
        self._down_since = None
        self._fired = False

    def long_press(self) -> bool:
        """True once per press, the moment it passes the hold threshold."""
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_poll) < self._interval_ms:
            return False
        self._last_poll = now

        if not pressed():
            self._down_since = None
            self._fired = False
            return False

        if self._down_since is None:
            self._down_since = now
            return False

        if not self._fired and time.ticks_diff(now, self._down_since) >= self._hold_ms:
            self._fired = True
            return True

        return False
