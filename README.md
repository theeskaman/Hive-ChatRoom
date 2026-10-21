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
- **Security status:** the 1.9.3 Stable source has been updated to hash account passwords with PBKDF2-HMAC-SHA256, migrate legacy user records, remove weak demo accounts, use expiring in-memory session tokens, and keep credentials out of URLs. This has not been tested on the physical Pico/ESP hardware yet.
- **Versions 1.9.2 and earlier are historical archives and retain legacy authentication patterns.** Do not use them where untrusted devices can access the network; prefer 1.9.3 for evaluation of the maintained security fixes.
- The firmware still uses plain HTTP and is **not safe for Internet exposure**. Run it only on a trusted, isolated local network; do not port-forward it or expose it directly to the public Internet.
- Versions with `ADMIN_PASS` require a strong, unique value of at least 12 characters configured before first boot. Never reuse the Wi-Fi password.
- On first boot, 1.9.3 migrates legacy `users.txt` records to password hashes and removes weak accounts/credentials. Back up `users.txt` and other device-side data before upgrading; weak legacy accounts may need to register again.
- Firmware upgrades do not automatically remove device-side files such as `messages.txt`, sensor logs, or configuration files. Inspect them before replacing firmware or resetting the device.
- Review the code and test on the target hardware. Alpha/beta versions are for evaluation.

## Troubleshooting

- **Wi-Fi does not connect:** check the 2.4 GHz network name/password, ESP-01S 3.3 V supply, TX/RX crossover, shared ground, and the UART pins/baud rate expected by the selected source.
- **The page does not open:** confirm the serial console reports a Wi-Fi IP address, then use that IP from a device on the same LAN.
- **Pages/assets are missing:** copy all and only companion files belonging to the selected version, preserving names and paths.
- **Sensor readings are unavailable:** confirm that the version supports the sensor and that it is connected to the configured pin.

## Release maintainer note

The published tag refs currently point to shared repository snapshots. The eight `release-snapshot/*` branches now contain isolated version packages. This connection cannot edit or delete tag refs directly; run the following from a local clone after reviewing the snapshots to make the built-in Release source archives version-specific:

```sh
git fetch origin --tags
git tag -f 1.6-stable 65881c6fece0a04574ea74f1ad6f204ad6f9d3fc
git tag -f 1.7.2 38ba8f4c276a8fa0632f4ee4bcbad8ca234b5f67
git tag -f 1.8.3 9a372b5aa2e0ed910da35b20da0ba8079f38f895
git tag -f 1.8.3-lite bb4517203de0c2de23178e93d9e5cec7b4c40b3d
git tag -f 1.8.4 cc834a76c5ff87bdbef7a8c8203d286f2cc3fa69
git tag -f 1.9.1 85175a0808974bb5672f0a6055f8e40e707e29c5
git tag -f 1.9.2 2d6101ef1fcaa5ac4d1a4b3759f759eb983c07c1
git tag -f 1.9.3 da507548baff9fe5d93b925c63f4e96863db5aea

git push --force origin \
  refs/tags/1.6-stable:refs/tags/1.6-stable \
  refs/tags/1.7.2:refs/tags/1.7.2 \
  refs/tags/1.8.3:refs/tags/1.8.3 \
  refs/tags/1.8.3-lite:refs/tags/1.8.3-lite \
  refs/tags/1.8.4:refs/tags/1.8.4 \
  refs/tags/1.9.1:refs/tags/1.9.1 \
  refs/tags/1.9.2:refs/tags/1.9.2 \
  refs/tags/1.9.3:refs/tags/1.9.3
```

This rewrites existing public tags. Confirm the commit IDs first, then change the standalone ZIP links above from `refs/heads/release-snapshot/...` to `refs/tags/...`. Once those tag links work, these already-merged/archive branches are redundant and can be removed to reduce clutter:

```sh
git push origin --delete \
  initial-versions \
  versions-1.6-to-1.7 \
  security-cleanup-1.1-to-1.5 \
  security-cleanup-1.6-to-1.7 \
  security-readme-release-fix
```

Keep `release-snapshot/*` until you have verified the tags and switched the download links. The source folders under `versions/` on `main` now provide the complete historical source index.

## License

MIT. See [LICENSE](LICENSE).
