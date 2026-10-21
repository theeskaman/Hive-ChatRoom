# Hive-ChatRoom 1.9.1 — Historical Archive

## Security status: legacy / not recommended for deployment

This is a preserved historical build. It uses legacy authentication and stores user passwords in plain-text files; some browser requests also send credentials in URLs. These patterns can expose passwords in browser history, logs, and other request metadata.

**Do not use this build on an untrusted network and never expose it to the public Internet.** Prefer the maintained 1.9.3 source for evaluation. It is still a small-device project using plain HTTP and must remain on a trusted, isolated LAN.

Before any test, replace `YOUR_WIFI_SSID` and `YOUR_WIFI_PASSWORD` in `main.py`. This package is archived for compatibility/history, not a security-supported release.


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
