import time


class ShakeDetector:
    """
    Detects a deliberate shake: several sharp accelerations in quick succession.

    A resting cube reads ~1g total and even a brisk roll stays close to that,
    so the threshold sits well above anything normal handling produces. Uses
    squared magnitude to avoid a square root on every sample.
    """

    def __init__(self, threshold_g: float, count: int, window_ms: int, refractory_ms: int = 150):
        self._threshold_sq = threshold_g * threshold_g
        self._count = count
        self._window_ms = window_ms
        self._refractory_ms = refractory_ms
        self._spikes = []
        self._last_spike = None

    def update(self, ax: float, ay: float, az: float) -> bool:
        """Feed one sample. True once, when the gesture completes."""
        now = time.ticks_ms()

        if ax * ax + ay * ay + az * az >= self._threshold_sq:
            # One shake is a sustained spike across many samples; the
            # refractory period stops it counting as several.
            if self._last_spike is None or time.ticks_diff(now, self._last_spike) >= self._refractory_ms:
                self._last_spike = now
                self._spikes.append(now)

        self._spikes = [t for t in self._spikes if time.ticks_diff(now, t) <= self._window_ms]

        if len(self._spikes) >= self._count:
            self.reset()
            return True

        return False

    def reset(self):
        self._spikes = []
        self._last_spike = None
