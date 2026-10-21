# Hive-ChatRoom

A local-network chat server for a Raspberry Pi Pico with an ESP-01S/ESP8266 Wi-Fi module. The repository preserves historical firmware versions; features and hardware details vary by version.

## Quick start

1. Choose **one** version from the version index below. Do not mix `main.py`, HTML files, or support files from different versions.
2. Read the short README inside the chosen version folder (where provided) and inspect its pin/UART constants before wiring hardware.
3. Open that version's `main.py` and configure `YOUR_WIFI_SSID` and `YOUR_WIFI_PASSWORD`. If the version defines `ADMIN_PASS`, replace `CHANGE_ME_TO_A_LONG_UNIQUE_PASSWORD` with a strong, unique secret before first boot.
4. Copy `main.py` to the Pico as `/main.py`. Copy only the companion files listed for that exact version, preserving their names.
5. Restart the Pico, read the serial console for connection status and the device's local IP address, then open `http://DEVICE_IP/` from a device on the same local network.

### Hardware checklist

- Raspberry Pi Pico with compatible MicroPython firmware.
- ESP-01S/ESP8266 with working AT-command firmware and 3.3 V-compatible UART wiring.
- Stable regulated 3.3 V power for the ESP module, crossed UART TX/RX lines, and a shared ground.
- DHT sensor only for versions/configurations that support it.

**Never connect 5 V to ESP-01S power or signal pins.** UART pins, sensor pin numbers, and companion files differ across versions; verify the selected source before connecting hardware.

## Version index

All historical firmware folders are kept under `versions/` using one consistent layout.

| Version | Contents / status | Browse source |
| --- | --- | --- |
| 1.1 | Legacy firmware | [versions/1.1](versions/1.1/) |
| 1.2 | Legacy firmware | [versions/1.2](versions/1.2/) |
| 1.3 | Legacy firmware | [versions/1.3](versions/1.3/) |
| 1.3.1 | Legacy firmware | [versions/1.3.1](versions/1.3.1/) |
| 1.4-alpha | Alpha archive | [versions/1.4-alpha](versions/1.4-alpha/) |
| 1.4-beta | Beta archive | [versions/1.4-beta](versions/1.4-beta/) |
| 1.4-m-beta | Beta archive | [versions/1.4-m-beta](versions/1.4-m-beta/) |
| 1.5-alpha | Alpha archive | [versions/1.5-alpha](versions/1.5-alpha/) |
| 1.6-beta | Beta archive | [versions/1.6-beta](versions/1.6-beta/) |
| 1.6-stable | Historical stable | [versions/1.6-stable](versions/1.6-stable/) |
| 1.7 | Legacy firmware | [versions/1.7](versions/1.7/) |
| 1.7.1 | Legacy firmware | [versions/1.7.1](versions/1.7.1/) |
| 1.7.2 | Legacy firmware | [versions/1.7.2](versions/1.7.2/) |
| 1.8-beta | Beta archive | [versions/1.8-beta](versions/1.8-beta/) |
| 1.8.1 | Legacy firmware | [versions/1.8.1](versions/1.8.1/) |
| 1.8.2 | Legacy firmware | [versions/1.8.2](versions/1.8.2/) |
| 1.8.3 | Standard + Lite | [versions/1.8.3](versions/1.8.3/) |
| 1.8.4 Alpha | Alternate server and UIs | [versions/1.8.4](versions/1.8.4/) |
| 1.9.1 | Historical firmware | [versions/1.9.1](versions/1.9.1/) |
| 1.9.2 Alpha | Historical Alpha | [versions/1.9.2](versions/1.9.2/) |
| 1.9.3 Stable | Latest archived release | [versions/1.9.3](versions/1.9.3/) |

### Standalone release downloads

These ZIPs contain only the files for the named release and a short installation note:

| Release | Package |
| --- | --- |
| 1.6 Stable | [Download ZIP](https://github.com/theeskaman/Hive-ChatRoom/archive/refs/heads/release-snapshot/1.6-stable.zip) |
| 1.7.2 | [Download ZIP](https://github.com/theeskaman/Hive-ChatRoom/archive/refs/heads/release-snapshot/1.7.2.zip) |
| 1.8.3 | [Download ZIP](https://github.com/theeskaman/Hive-ChatRoom/archive/refs/heads/release-snapshot/1.8.3.zip) |
| 1.8.3 Lite | [Download ZIP](https://github.com/theeskaman/Hive-ChatRoom/archive/refs/heads/release-snapshot/1.8.3-lite.zip) |
| 1.8.4 Alpha | [Download ZIP](https://github.com/theeskaman/Hive-ChatRoom/archive/refs/heads/release-snapshot/1.8.4.zip) |
| 1.9.1 | [Download ZIP](https://github.com/theeskaman/Hive-ChatRoom/archive/refs/heads/release-snapshot/1.9.1.zip) |
| 1.9.2 Alpha | [Download ZIP](https://github.com/theeskaman/Hive-ChatRoom/archive/refs/heads/release-snapshot/1.9.2.zip) |
| 1.9.3 Stable | [Download ZIP](https://github.com/theeskaman/Hive-ChatRoom/archive/refs/heads/release-snapshot/1.9.3.zip) |

## Security and privacy

- The source should contain placeholders, never real Wi-Fi credentials. Change the router password if a previous password was committed publicly: updating current files does not remove it from Git history or old downloaded archives.
- These are historical MicroPython builds, **not an Internet-hardened service**. Some archived releases use legacy authentication and data handling. Until an exact release has been security-tested, run it only on a trusted isolated local network; do not port-forward it or expose it directly to the public Internet.
- Versions with `ADMIN_PASS` require a strong, unique value configured before first boot. Do not reuse the Wi-Fi password.
- Firmware upgrades do not automatically remove device-side files such as `users.txt`, `messages.txt`, or configuration/log files. Back them up and inspect them before replacing firmware or resetting the device.
- Review the code and test on the target hardware. Alpha/beta versions are for evaluation.

## Troubleshooting

- **Wi-Fi does not connect:** check the 2.4 GHz network name/password, ESP-01S 3.3 V supply, TX/RX crossover, shared ground, and the UART pins/baud rate expected by the selected source.
- **The page does not open:** confirm the serial console reports a Wi-Fi IP address, then use that IP from a device on the same LAN.
- **Pages/assets are missing:** copy all and only companion files belonging to the selected version, preserving names and paths.
- **Sensor readings are unavailable:** confirm that the version supports the sensor and that it is connected to the configured pin.

## Release maintainer note

The published GitHub tag refs were found to point to shared repository snapshots rather than version-specific trees. The `release-snapshot/*` branches are isolated packages, but the existing tags must be retargeted in GitHub before the Releases' built-in “Source code (zip)” archives are fixed. The exact target commits are documented in the commit history; do not move tags without reviewing the release package first.

## License

MIT. See [LICENSE](LICENSE).
