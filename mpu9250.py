import time
from machine import I2C

MPU9250_ADDR = 0x68

# Register addresses
PWR_MGMT_1  = 0x6B
ACCEL_XOUT_H = 0x3B
ACCEL_CONFIG = 0x1C
WHO_AM_I    = 0x75

# Accelerometer scale: ±2g → 16384 LSB/g
ACCEL_SCALE = 16384.0


class MPU9250:
    def __init__(self, i2c: I2C, addr: int = MPU9250_ADDR):
        self._i2c = i2c
        self._addr = addr
        self._buf = bytearray(6)
        self._wake()

    def _write(self, reg: int, value: int):
        self._i2c.writeto_mem(self._addr, reg, bytes([value]))

    def _read(self, reg: int, n: int) -> bytearray:
        return self._i2c.readfrom_mem(self._addr, reg, n)

    def _wake(self):
        # Clear sleep bit
        self._write(PWR_MGMT_1, 0x00)
        time.sleep_ms(100)
        # Set accel range to ±2g (default, most sensitive)
        self._write(ACCEL_CONFIG, 0x00)

    def whoami(self) -> int:
        return self._read(WHO_AM_I, 1)[0]

    def read_accel(self) -> tuple[float, float, float]:
        """Return (ax, ay, az) in units of g."""
        data = self._read(ACCEL_XOUT_H, 6)
        ax = _to_signed(data[0] << 8 | data[1]) / ACCEL_SCALE
        ay = _to_signed(data[2] << 8 | data[3]) / ACCEL_SCALE
        az = _to_signed(data[4] << 8 | data[5]) / ACCEL_SCALE
        return ax, ay, az


def _to_signed(val: int) -> int:
    return val if val < 32768 else val - 65536
