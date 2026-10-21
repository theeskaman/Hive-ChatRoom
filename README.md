# Hive-ChatRoom

A lightweight, local-network chat room built around a **Raspberry Pi Pico** paired with an **ESP-01S Wi-Fi module**. Hive-ChatRoom is intended for small groups of devices on the same local network, with support for up to **8 simultaneous devices**.

This branch, `versions-1.6-to-1.7`, is the version-transition branch for the 1.6–1.7 code line. Its documentation is scoped to this branch; check the source and configuration in this branch before assuming behavior or compatibility from another version.

## Why Hive-ChatRoom?

Hive-ChatRoom was developed during the 88-day internet blackout in Iran as an attempt to provide a simple way to communicate locally without depending on government-based messaging applications or an internet connection.

Potential use cases include:

- Exchanging short messages between family members or a small group.
- Synchronizing clipboard text between devices, where supported by the client workflow.
- Communicating over a local network when internet access is unavailable.

## Hardware

The project is built around:

- **Raspberry Pi Pico** — main microcontroller.
- **ESP-01S Wi-Fi module** — network connectivity / Wi-Fi interface.
- **Client devices** — up to 8 devices on the local network.

Check the firmware and wiring/configuration files in this branch for the exact pin assignments, power requirements, and module settings. Do not assume that wiring or configuration from another branch is interchangeable.

## Network and privacy scope

- Designed for use on a **local network**.
- The stated capacity is up to **8 devices simultaneously**.
- The project aims to reduce reliance on internet-hosted messaging services.

**Security note:** Local-network operation does not by itself guarantee encryption, authentication, or confidentiality. Do not use Hive-ChatRoom to transmit sensitive information unless you have reviewed the implementation and independently verified its security properties. Keep the device on a trusted network.

## Getting started

1. Check out this branch:
   ```bash
   git clone https://github.com/theeskaman/Hive-ChatRoom.git
   cd Hive-ChatRoom
   git switch versions-1.6-to-1.7
   ```
2. Review the source files and any firmware/configuration instructions included in this branch.
3. Assemble the Raspberry Pi Pico and ESP-01S hardware according to the project’s actual wiring and power requirements.
4. Configure the Wi-Fi/network settings as required by the source.
5. Build and flash the firmware using the toolchain appropriate to the files in this branch.
6. Connect client devices to the intended local network and verify communication with non-sensitive test messages.

> Build commands, required libraries, pin mappings, and Wi-Fi configuration keys are intentionally not guessed here. Use the files present in this branch as the source of truth; document exact commands here once they have been verified against the current code.

## Branch/version notes

- **Branch:** `versions-1.6-to-1.7`
- **Scope:** the 1.6-to-1.7 version line.
- This README describes the project and branch scope; it does not claim that every planned feature is implemented or tested.
- When making changes, keep documentation aligned with the actual firmware, hardware wiring, and supported client behavior.

## Contributing

When contributing to this branch:

1. Keep changes focused and compatible with the hardware constraints.
2. Document configuration changes and any new dependencies.
3. Test on the target hardware where possible, including behavior with multiple clients.
4. Avoid documenting a feature as supported until it has been verified.

## License

No license terms are asserted by this README. Check the repository’s license files or obtain clarification from the maintainer before redistributing or reusing the project.
