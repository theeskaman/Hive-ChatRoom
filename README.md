# HIVE — Local Wi-Fi Chat Room

HIVE is a small local-network chat room built around a Raspberry Pi Pico and an ESP-01S Wi-Fi module. The project was created as a practical way for nearby devices to exchange short messages without depending on a hosted chat service. The original design targets up to eight devices on the same local network.

The project grew during the 88-day internet blackout in Iran, when privacy and access to independent communication tools mattered especially. HIVE can be used for short family messages and simple clipboard-sharing workflows, provided the devices are connected to the same network.

## Hardware and software

- Raspberry Pi Pico running MicroPython
- ESP-01S Wi-Fi module, configured to match the firmware
- Optional DHT11 temperature/humidity sensor (the firmware versions shown here use GPIO 0 by default)
- Browser on a phone, tablet, or computer connected to the same local network

Features vary by version. Depending on the firmware, they include message history, pinned messages, reactions, user roles, moderation controls, temperature logging, and maintenance/update pages.

## Version history

Each version has its own folder. In firmware folders, `main.py` is the default MicroPython entry point to copy to the Pico. Where a version includes an additional variant or interface, its filename and folder README explain the difference.

| Version | What is included |
| --- | --- |
| [1.8.3](1.8.3/) | Standard firmware and a lighter Lite variant |
| [1.8.4](1.8.4/) | Primary firmware, an alternative server implementation, and two distinct chat UI designs |
| [1.9.1](1.9.1/) | Firmware and chat, maintenance, and update pages |
| [1.9.2](1.9.2/) | Firmware and chat, maintenance, and update pages |
| [1.9.3](1.9.3/) | Stable-labelled firmware, chat UI, maintenance/update pages, and login news text |

Older 1.8-era snapshots are retained at the repository root for historical reference. The `initial-versions` and `versions-1.6-to-1.7` branches contain the earlier archived versions.

## Getting started

1. Choose the version folder that matches the features you need.
2. Read that folder's `README.md` before copying files to the board.
3. Open the selected firmware and replace the Wi-Fi settings and any default credentials with your own values.
4. Copy the chosen firmware to the Pico as `main.py`.
5. Copy the HTML/text assets required by that firmware to the location expected by its file-serving code.
6. Restart the board and test the chat from a second device on the same local network.

The versions are historical source snapshots, not a guarantee that every combination of firmware, ESP-01S configuration, and browser assets has been tested together. Test the exact version on your hardware before relying on it.

## Security notes

HIVE is designed for local-network use. Before running it, change the Wi-Fi credentials and all default account or administrator credentials found in the selected source file. Do not expose the device directly to the public internet without adding and reviewing appropriate security protections.

## License

This project is distributed under the MIT License. See [LICENSE](LICENSE).
