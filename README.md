# Hive-ChatRoom

A local-network chat room for a Raspberry Pi Pico connected to an ESP-01S Wi-Fi module. Depending on the version, it includes message history, replies, notifications, a browser chat interface, sensor/status information, user accounts, reactions, pinning, maintenance mode, or update tools.

> **Important release-download note (checked 2026-10-21):** the eight published Releases do not currently point to eight independent version snapshots. The tags `1.6-stable` and `1.7.2` point to the same commit, and the tags `1.8.3`, `1.8.3-lite`, `1.8.4`, `1.9.1`, `1.9.2`, and `1.9.3` point to another shared commit. Each Release also has no uploaded release-specific assets. Until the tag refs are corrected in GitHub, **use the exact version-file links below instead of relying on a Release's “Source code (zip)” archive to obtain only one version**. A source archive represents the full repository tree at its tag, not a curated one-version package.

## Getting Started

### 1. Hardware and prerequisites

You need:

- A Raspberry Pi Pico running a compatible MicroPython firmware.
- An ESP-01S / ESP8266 module with working AT-command firmware.
- A regulated, stable 3.3 V supply suitable for the ESP-01S, appropriate UART wiring, and a shared ground.
- A USB data cable and a computer with a MicroPython file-transfer tool such as Thonny.
- A DHT sensor only if you plan to use a version and wiring that supports it.

Connect the Pico and ESP-01S UART TX/RX lines to the pins expected by the selected version, crossing TX to RX, and connect their grounds. **Do not apply 5 V to ESP-01S power or signal pins.** Pin assignments, UART settings, and sensor support can differ between versions; check the constants and UART setup in that version's `main.py` before wiring the hardware. Do not assume that a wiring diagram or settings for one version apply to every other version.

### 2. Choose and download one version

Open the file link in the version table below and use the browser's download/save option. The older version files live on archive branches; versions 1.8 and later live under `versions/`. Keep all files from the same version together and do not combine `main.py` or HTML files from different versions.

For the eight published releases:

| Release | Exact source file(s) |
| --- | --- |
| **1.6 Stable** | [main.py](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-cleanup-1.1-to-1.5/versions/1.6-stable/main.py) |
| **1.7.2** | [main.py](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-cleanup-1.6-to-1.7/versions/1.7.2/main.py) |
| **1.8.3** | [Standard main.py](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.8.3/main.py) |
| **1.8.3 Lite** | [main_lite.py](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.8.3/main_lite.py) |
| **1.8.4 Alpha** | [main.py](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.8.4/main.py), [server_alternative.py](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.8.4/server_alternative.py), [chat.html](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.8.4/chat.html), [chat-alternative.html](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.8.4/chat-alternative.html) |
| **1.9.1** | [main.py](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.9.1/main.py), [chat.html](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.9.1/chat.html), [maintenance.html](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.9.1/maintenance.html), [update.html](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.9.1/update.html) |
| **1.9.2 Alpha** | [main.py](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.9.2/main.py), [chat.html](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.9.2/chat.html), [maintenance.html](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.9.2/maintenance.html), [update.html](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.9.2/update.html) |
| **1.9.3 Stable** | [main.py](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.9.3/main.py), [chat.html](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.9.3/chat.html), [maintenance.html](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.9.3/maintenance.html), [update.html](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.9.3/update.html), [news.txt](https://raw.githubusercontent.com/theeskaman/Hive-ChatRoom/security-readme-release-fix/versions/1.9.3/news.txt) |

Other archived versions are available here: [versions 1.1–1.5](https://github.com/theeskaman/Hive-ChatRoom/tree/security-cleanup-1.1-to-1.5/versions) · [versions 1.6–1.7.2](https://github.com/theeskaman/Hive-ChatRoom/tree/security-cleanup-1.6-to-1.7/versions) · [versions 1.8 and later](https://github.com/theeskaman/Hive-ChatRoom/tree/security-readme-release-fix/versions).

### 3. Configure Wi-Fi and administrator access before running

Open the downloaded version's `main.py` in a text editor and find the Wi-Fi constants near the top. Replace the placeholders with the credentials for the 2.4 GHz network that the ESP-01S should join:

- `SSID = "YOUR_WIFI_SSID"` — the exact Wi-Fi network name.
- `PASSWORD = "YOUR_WIFI_PASSWORD"` — that network's password.

Do not upload or commit a copy containing your real Wi-Fi password to a public repository. These source files are intended to contain placeholders, not personal network credentials.

Versions that define `ADMIN_PASS` use the placeholder `CHANGE_ME_TO_A_LONG_UNIQUE_PASSWORD`. Replace it with a strong, unique password before deployment. In the updated 1.8.x versions, admin-only actions are disabled while this placeholder remains. In 1.9.1–1.9.3, no default `admin/nigga` or `test/test123` account is created; configure `ADMIN_PASS` before the first boot if you need admin access. If the device already has a `users.txt` file from an older run, back it up and inspect it before reusing it: updating the source file does not erase old accounts or passwords stored on the device.

### 4. Copy files to the Pico

1. Connect the Pico over USB and open it in Thonny (or another MicroPython file-transfer tool).
2. Make a backup of any existing `main.py`, chat history, configuration, and user-data files before replacing them.
3. Copy the selected version's firmware onto the Pico as `/main.py`.
4. For **1.8.3 Lite**, copy `main_lite.py` and rename it to `main.py` on the device. Do not run the standard and Lite entry points separately.
5. For versions with companion HTML/text files, copy the files listed for that version to the device filesystem with their names unchanged. Use the HTML variant intended for the selected firmware. Do not install `server_alternative.py` as a second boot program; it is an alternative implementation for deliberate testing.
6. Save the files, restart the Pico, and open the serial console to review startup messages.

The exact assets vary by version. Versions 1.8.3 and earlier may embed more of the web UI inside `main.py`; 1.8.4 and 1.9.x have additional UI/support files listed above. Use the selected version's own set.

### 5. Connect from a browser

After startup, check the serial output for Wi-Fi connection status and the device's local IP address. From a phone or computer on the **same local network**, open `http://DEVICE_IP/`, replacing `DEVICE_IP` with the address reported by the device. Port 80 is used by the versions documented here unless the selected source says otherwise.

### 6. Security and privacy checklist

- The original source contained a personal Wi-Fi SSID/password and weak hard-coded administrator passwords. This cleanup replaces those source literals with placeholders, but **it cannot revoke a password that has already appeared in repository history or old published Release archives**. Change the exposed Wi-Fi password on your router/access point now, and update any device using the old password.
- Never expose this service directly to the public Internet or forward its port from your router. Treat it as a local-network project, not an Internet-hardened chat service.
- Some historical versions store credentials or application data in plain-text files on the device. Restrict physical access to the Pico and back up files before deleting or replacing them. Do not assume an upgrade automatically migrates or securely erases existing user data.
- Use a unique admin password. Do not reuse your Wi-Fi password, personal password, or a password used by another service.
- Review the code and test it on the exact hardware before relying on it. Alpha releases (including 1.8.4 and 1.9.2) are intended for evaluation.

### 7. Troubleshooting

- **Wi-Fi will not connect:** check the 2.4 GHz SSID/password spelling, stable 3.3 V power for the ESP-01S, TX/RX wiring, common ground, and the UART pins/baud rate expected by the selected source.
- **The browser cannot open the page:** verify that the serial console reports a connected Wi-Fi network and an IP address, then use that IP from a device on the same LAN.
- **UI elements or pages are missing:** make sure every companion file came from the same version and is saved under the expected name/path.
- **Admin functions are unavailable:** set a unique `ADMIN_PASS` before first boot where supported. If the device already has `users.txt`, inspect its existing contents and back it up before changing it.
- **Sensor values are missing:** confirm that the selected version supports your sensor and that the sensor is connected to the pin configured by `DHT_PIN`.

## Version archive

The repository preserves historical implementations rather than making every version identical. For reproducible testing, select one version directory and keep its firmware and companion files together. Version-specific feature lists are documented on each [GitHub Release page](https://github.com/theeskaman/Hive-ChatRoom/releases).

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
