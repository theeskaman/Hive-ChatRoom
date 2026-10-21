# HIVE 1.8.3

This folder contains the standard and Lite firmware variants for HIVE 1.8.3.

## Files

- `main.py` — standard MicroPython firmware for the Raspberry Pi Pico and ESP-01S.
- `main_lite.py` — lighter alternative for the same version. Use this instead of `main.py` when you specifically want the Lite build; do not run both as separate entry points.

## Setup

1. Open the firmware variant you intend to use and update the Wi-Fi settings and administrator credential before deployment.
2. Copy the chosen firmware to the Pico as `main.py` (rename `main_lite.py` to `main.py` if using Lite).
3. Check the configured DHT11 pin and connect the hardware accordingly.
4. Restart the Pico and test from a device on the same local network.

The files are preserved source variants; hardware compatibility and behavior should be tested on the target board.
