# HIVE 1.8.4

HIVE 1.8.4 includes a primary firmware build, an alternative server implementation, and two distinct chat interfaces. The two HTML files are intentionally kept: they are different UI designs, not duplicate files to remove.

## Files

- `main.py` — primary MicroPython firmware entry point for the Raspberry Pi Pico.
- `server_alternative.py` — alternative server implementation for comparison/testing. It is not the default boot file; use it only if you deliberately choose that implementation.
- `chat.html` — primary chat interface.
- `chat-alternative.html` — alternative chat interface/design.

## Setup

1. Configure the Wi-Fi credentials and administrator credential in the firmware before use.
2. Copy `main.py` to the Pico as the boot file.
3. Keep the HTML file expected by the firmware available to the device. If switching UI designs, verify the firmware's file-serving path and use the matching HTML file.
4. Test the selected interface and server on the target hardware.

The alternative server and alternative UI are separate choices; their names identify their roles and do not imply that both server files should be run together.
