# Wiring: e-Paper Driver HAT Rev2.3 → Raspberry Pi Pico 2W

## Connection Table

| HAT Wire | Wire Color | Pico GPIO | Pico Physical Pin | Notes |
|----------|------------|-----------|-------------------|-------|
| VCC      | Red        | 3.3V      | Pin 36            | Display logic power |
| GND      | Black      | GND       | Pin 38            | Ground |
| PWR      | Brown      | GP14      | Pin 19            | Display power enable — controlled by code |
| DIN      | Blue       | GP11      | Pin 15            | SPI1 MOSI (data in) |
| CLK      | Yellow     | GP10      | Pin 14            | SPI1 SCK (clock) |
| CS       | Orange     | GP9       | Pin 12            | SPI1 chip select |
| DC       | Green      | GP8       | Pin 11            | Data / command select |
| RST      | White      | GP12      | Pin 16            | Hardware reset |
| BUSY     | Purple     | GP13      | Pin 17            | Busy signal (LOW = busy, HIGH = ready) |

## Pico 2W Pin Diagram

```
                    ┌─────────────┐
              VBUS  │ 40       39 │ VSYS
         GND (BLK) ←│ 38       37 │ 3V3_EN
        3.3V (RED) ←│ 36       35 │ ADC_VREF
                    │ 34       33 │ GND
                    │ 32       31 │ GP26
               RUN  │ 30       29 │ GP22
               GND  │ 28       27 │ GP21
                    │ 26       25 │ GP20
                    │ 24       23 │ GND
                    │ 22       21 │ GP16
                    │ 20       19 │ GP14  ←── PWR (BRN)
               GND  │ 18       17 │ GP13  ←── BUSY (PRP)
  RST (WHT) ──GP12  │ 16       15 │ GP11  ←── DIN (BLU)
  CLK (YLW) ──GP10  │ 14       13 │ GND
   CS (ORG)  ──GP9  │ 12       11 │ GP8   ──DC (GRN)
               GP7  │ 10        9 │ GP6
               GND  │  8        7 │ GP5
               GP4  │  6        5 │ GP3
               GP2  │  4        3 │ GND
               GP1  │  2        1 │ GP0
                    └─────[ USB ]─┘
```

## Notes

- **PWR** (GP14) controls the display's internal power converter. The code drives it HIGH before each update and LOW after the display enters deep sleep, cutting power entirely between refreshes.
- **DIN** is MOSI only — this display is write-only, so MISO is not connected.
- These pin assignments match the values in `config.py`. If you rewire to different GPIO pins, update the `PIN_*` and `SPI_*` constants in that file.
