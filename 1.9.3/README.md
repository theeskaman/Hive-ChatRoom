# HIVE 1.9.3

HIVE 1.9.3 is the stable-labelled build in this repository. Its firmware includes chat and message handling, pinned messages, reactions, user roles, moderation settings, configurable logging, a news panel, and maintenance/update pages.

## Files

- `main.py` — MicroPython firmware entry point for the Raspberry Pi Pico and ESP-01S.
- `chat.html` — main browser chat interface.
- `maintenance.html` — maintenance interface.
- `update.html` — update-management interface.
- `news.txt` — text shown in the login/news panel.

## Setup and security

1. Change the Wi-Fi settings and all default account credentials in the firmware before deployment.
2. Copy `main.py` to the Pico and ensure the HTML and text assets required by the firmware are also present on the device.
3. Confirm that the ESP-01S firmware and serial/network configuration match the code.
4. Test login, chat, maintenance, and update flows on the target hardware before relying on the system.

This release is intended for a local network. Do not expose it directly to the public internet without a separate security review.
