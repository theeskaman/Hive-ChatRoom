# Hive-ChatRoom 1.9.2 Alpha — Historical Archive

## Security status: legacy Alpha / not recommended for deployment

This is a preserved Alpha build. It retains legacy authentication and plain-text password storage, and some browser requests send credentials in URLs. This can expose secrets in browser history and request logs.

**Do not use this build on an untrusted network and never expose it to the public Internet.** Prefer the maintained 1.9.3 source for evaluation. Even 1.9.3 uses plain HTTP and should stay on a trusted, isolated LAN.

Before testing, replace `YOUR_WIFI_SSID` and `YOUR_WIFI_PASSWORD` in `main.py`, and set `ADMIN_PASS` to a strong, unique value. This package is preserved for historical compatibility, not security support.


## Files

This ZIP contains only the files needed for this version:

- `main.py` — firmware entry point
- `chat.html` — chat interface
- `maintenance.html` — maintenance page
- `update.html` — update manager

## Install

1. Back up device-side history, users, configuration and log files.
2. Configure Wi-Fi credentials and review the code before first boot.
3. Copy the included files to the Pico, keeping the names unchanged.
4. Restart and test only on a trusted local network.

See the main repository [README](https://github.com/theeskaman/Hive-ChatRoom/blob/main/README.md) for hardware notes and troubleshooting.
