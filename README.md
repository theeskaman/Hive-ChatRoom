# Hive-ChatRoom

A type of chat room that uses a Raspberry Pi Pico paired with an ESP-01S Wi-Fi module as the backend server. It can be used on a local network by up to 8 devices at the same time.

I developed this code during the 88-day widespread internet blackout in Iran to avoid relying on government-backed applications that offer almost no privacy. It can be used to sync the clipboard between multiple devices or to exchange short messages among family members.

## Versions

All versioned code is kept in the `versions/` folder, with a separate folder for each version. The firmware file is named `main.py`, so it is easy to identify what should be copied to the Raspberry Pi Pico. Some versions include extra files for the browser interface or an alternative build.

- [1.8-beta](versions/1.8-beta/) — early 1.8 beta build.
- [1.8.1](versions/1.8.1/) — 1.8.1 firmware.
- [1.8.2](versions/1.8.2/) — 1.8.2 firmware.
- [1.8.3](versions/1.8.3/) — standard firmware and a Lite alternative (`main_lite.py`).
- [1.8.4](versions/1.8.4/) — firmware, an alternative server implementation, and two different chat interfaces (`chat.html` and `chat-alternative.html`). Both interfaces are kept intentionally.
- [1.9.1](versions/1.9.1/) — firmware with chat, maintenance, and update pages.
- [1.9.2](versions/1.9.2/) — firmware with chat, maintenance, and update pages.
- [1.9.3](versions/1.9.3/) — firmware with chat, maintenance, and update pages, plus `news.txt` for the login news panel.

## Getting started

1. Choose a version and open its folder.
2. Update the Wi-Fi settings and any default credentials in `main.py` before using it.
3. Copy that version's `main.py` to the Pico. If you want the Lite build in 1.8.3, use `main_lite.py` as the board's `main.py` instead.
4. Copy the HTML and text files that belong to the same version to the locations expected by its firmware.
5. Restart the Pico and test the chat from another device connected to the same local network.

The files are kept as separate version snapshots, and the exact features differ between releases. Test the version you choose on your own Pico and ESP-01S setup before relying on it.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
