# Hardware Setup

## Board

Seeed Studio XIAO nRF52840 Plus running the Seeed nRF52 mbed-enabled Boards package in Arduino IDE 2.x on macOS.

**Arduino IDE settings:**

| Setting | Value |
|---|---|
| Board | Seeed XIAO BLE Sense — nRF52840 |
| USB Stack | TinyUSB |
| Upload Method | DFU Bootloader |

To upload: double-press the RESET button until the LED pulses, then click Upload.

---

## Microphones

Two analog capacitive microphones soldered directly to the board.

| Mic | Wire | Pin | Nostril |
|---|---|---|---|
| MIC1 | Yellow | A0 (D0) | Left |
| MIC2 | Blue | A1 (D1) | Right |
| Both VCC | — | 3.3V | — |
| Both GND | — | GND | — |

---

## Tobii Pro Glasses 2

The Recording Unit connects to your Mac via WiFi.

1. Power on the Recording Unit
2. On Mac — join the network named `TobiiProGlasses2_XXXXXXXX`
3. Find the IP address:

        python -c "from nasal_monitor import TobiiReader; TobiiReader.discover()"

4. Default IP is usually `192.168.71.50`

When connected to Tobii WiFi, the Mac has no internet access. This is expected behavior.

---

## Battery (optional)

For wireless wearable deployment, connect a 3.7V LiPo battery to the BAT+ and BAT- pads on the back of the board. The onboard BQ25101 chip handles charging automatically when USB is connected.

Recommended: 150mAh JST 1.25mm — approximately 8–10 hours runtime.