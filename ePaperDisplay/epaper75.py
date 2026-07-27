"""
Waveshare 7.5-inch V2 e-paper display driver for MicroPython (Pico 2W).
Resolution: 800x480, black/white.

Image buffer format (framebuf.MONO_HLSB):
  pixel = 0  →  bit = 0  →  WHITE on display
  pixel = 1  →  bit = 1  →  BLACK on display

Default wiring (Waveshare Pico e-Paper HAT):
  VCC  → 3.3V   GND  → GND
  PWR  → GP14   DIN  → GP11
  CLK  → GP10   CS   → GP9
  DC   → GP8    RST  → GP12
  BUSY → GP13
"""

from machine import Pin, SPI
import time


class EPaper75:
    WIDTH = 800
    HEIGHT = 480

    def __init__(self, spi_id, clk, mosi, cs, dc, rst, busy, pwr=None, baudrate=4_000_000):
        self.spi = SPI(spi_id, baudrate=baudrate, sck=Pin(clk), mosi=Pin(mosi))
        self.cs = Pin(cs, Pin.OUT, value=1)
        self.dc = Pin(dc, Pin.OUT, value=0)
        self.rst = Pin(rst, Pin.OUT, value=1)
        self.busy = Pin(busy, Pin.IN)
        # PWR controls the display's internal power converter.
        # Start LOW (off) so power_on() controls when the converter activates.
        self._pwr = Pin(pwr, Pin.OUT, value=0) if pwr is not None else None

    # ── low-level SPI helpers ────────────────────────────────────────────────

    def _cmd(self, cmd):
        self.dc.value(0)
        self.cs.value(0)
        self.spi.write(bytes([cmd]))
        self.cs.value(1)

    def _data(self, data):
        self.dc.value(1)
        self.cs.value(0)
        self.spi.write(bytes([data]) if isinstance(data, int) else bytes(data))
        self.cs.value(1)

    def _wait_busy(self):
        """Block until BUSY pin goes HIGH (display ready). Polls with GET_STATUS."""
        time.sleep_ms(10)
        self._cmd(0x71)
        while self.busy.value() == 0:
            self._cmd(0x71)
            time.sleep_ms(100)
        time.sleep_ms(20)

    # ── public API ───────────────────────────────────────────────────────────

    def power_on(self):
        """Enable the display's power converter. Always call before init()."""
        if self._pwr:
            self._pwr.value(1)
            time.sleep_ms(50)   # allow converter to stabilise before sending commands

    def power_off(self):
        """Cut power to the display's power converter. Call after sleep()."""
        if self._pwr:
            self._pwr.value(0)

    def reset(self):
        self.rst.value(1); time.sleep_ms(20)
        self.rst.value(0); time.sleep_ms(2)
        self.rst.value(1); time.sleep_ms(20)
        self._wait_busy()

    def init(self):
        """Full hardware initialisation. Call once at power-on and after sleep."""
        self.reset()

        self._cmd(0x06)                             # Booster soft start
        self._data([0x17, 0x17, 0x28, 0x17])

        self._cmd(0x01)                             # Power setting
        self._data([0x07, 0x07, 0x28, 0x17])        # VGH=20V VGL=-20V VDH=15V VDL=-15V

        self._cmd(0x04)                             # Power on
        time.sleep_ms(100)
        self._wait_busy()

        self._cmd(0x00); self._data(0x1F)           # Panel setting: KW mode
        self._cmd(0x61); self._data([0x03, 0x20, 0x01, 0xE0])  # Resolution 800x480
        self._cmd(0x15); self._data(0x00)           # Dual SPI off
        self._cmd(0x50); self._data([0x10, 0x07])   # VCOM and data interval
        self._cmd(0x60); self._data(0x22)           # TCON setting

    def init_part(self):
        """
        Lightweight init for partial (non-flashing) updates.
        Only valid while the panel is already powered and its RAM holds a
        previous image (from init()+display()/clear() or a prior
        display_partial() call) — do not call this after sleep()/power_off(),
        which wipe that RAM; use init() to recover from those instead.
        """
        self.reset()
        self._cmd(0x00); self._data(0x1F)           # Panel setting: KW mode
        self._cmd(0x04)                             # Power on
        time.sleep_ms(100)
        self._wait_busy()

    def display_partial(self, buf):
        """
        Push a full-frame update using the partial-refresh waveform: it
        transitions directly from the previous image to this one, with no
        black/white flash cycles. Ghosting/DC-imbalance accumulates over many
        partial updates — call init()+display() periodically (see
        config.FULL_REFRESH_EVERY in main.py) to reset it with a full flash.
        """
        self._cmd(0x50)
        self._data([0xA9, 0x07])                    # VCOM setting for partial mode

        self._cmd(0x91)                             # enter partial mode
        self._cmd(0x90)                              # partial window = full screen
        self._data([
            0x00, 0x00,                                             # x-start = 0
            (self.WIDTH - 1) >> 8, (self.WIDTH - 1) & 0xFF,          # x-end = 799
            0x00, 0x00,                                             # y-start = 0
            (self.HEIGHT - 1) >> 8, (self.HEIGHT - 1) & 0xFF,        # y-end = 479
            0x01,
        ])

        # Channel 0x13 expects the inverted image in partial mode (unlike a
        # full refresh, where 0x13 takes the raw buffer and only 0x10 —
        # unused here — is inverted).
        self._cmd(0x13)
        self.dc.value(1)
        self.cs.value(0)
        mv = memoryview(buf)
        inv = bytearray(512)
        for i in range(0, len(mv), 512):
            chunk = mv[i:i + 512]
            sz = len(chunk)
            for j in range(sz):
                inv[j] = chunk[j] ^ 0xFF
            self.spi.write(inv if sz == 512 else inv[:sz])
        self.cs.value(1)

        self._cmd(0x12)
        time.sleep_ms(100)
        self._wait_busy()

    def display(self, buf):
        """
        Push a 48000-byte image buffer and trigger a full refresh (~3–5 s).
        buf must be a bytearray in framebuf.MONO_HLSB format (bit=0 → white).

        Sends the inverted image to channel 0x10 (old-data) and the actual
        image to channel 0x13 (new-data) as required by the V2 controller.
        """
        mv = memoryview(buf)
        inv = bytearray(512)

        # Channel 0x10: inverted image (required for correct refresh waveform)
        self._cmd(0x10)
        self.dc.value(1)
        self.cs.value(0)
        for i in range(0, len(mv), 512):
            chunk = mv[i:i + 512]
            sz = len(chunk)
            for j in range(sz):
                inv[j] = chunk[j] ^ 0xFF
            self.spi.write(inv if sz == 512 else inv[:sz])
        self.cs.value(1)

        # Channel 0x13: actual image
        self._cmd(0x13)
        self.dc.value(1)
        self.cs.value(0)
        for i in range(0, len(mv), 4096):
            self.spi.write(mv[i:i + 4096])
        self.cs.value(1)

        self._cmd(0x12)
        time.sleep_ms(100)
        self._wait_busy()

    def clear(self):
        """Fill the display with white."""
        total = self.WIDTH * self.HEIGHT // 8   # 48000 bytes
        ff = bytes([0xFF] * 512)
        zero = bytes([0x00] * 512)

        self._cmd(0x10)
        self.dc.value(1); self.cs.value(0)
        for i in range(0, total, 512):
            self.spi.write(ff if i + 512 <= total else bytes([0xFF] * (total - i)))
        self.cs.value(1)

        self._cmd(0x13)
        self.dc.value(1); self.cs.value(0)
        for i in range(0, total, 512):
            self.spi.write(zero if i + 512 <= total else bytes([0x00] * (total - i)))
        self.cs.value(1)

        self._cmd(0x12)
        time.sleep_ms(100)
        self._wait_busy()

    def sleep(self):
        """
        Deep sleep (~1 µA). Image persists on display.
        Call power_off() after this, then power_on() + init() to wake.
        """
        self._cmd(0x50); self._data(0xF7)   # VCOM setting for sleep
        self._cmd(0x02)                      # Power off
        self._wait_busy()
        self._cmd(0x07); self._data(0xA5)   # Deep sleep
