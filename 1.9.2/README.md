# HIVE 1.9.2

This folder contains the 1.9.2 MicroPython firmware and its matching browser pages.

- `main.py` — firmware entry point for the Raspberry Pi Pico.
- `chat.html` — chat interface.
- `maintenance.html` — maintenance interface.
- `update.html` — update-management interface.

Before deployment, update the Wi-Fi settings and default credentials in `main.py`. Copy the firmware to the Pico as `main.py` and place the HTML assets where the firmware expects to load them. Test the combination on your hardware.
