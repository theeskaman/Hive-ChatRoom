# Hive-ChatRoom — Release source snapshot

This archive contains the source files for one Hive-ChatRoom release. Keep the included files together and do not mix files from other versions.

## Before first boot

1. Open `main.py` and replace `YOUR_WIFI_SSID` and `YOUR_WIFI_PASSWORD` with the credentials for your 2.4 GHz Wi-Fi network.
2. If the firmware defines `ADMIN_PASS`, replace `CHANGE_ME_TO_A_LONG_UNIQUE_PASSWORD` with a strong, unique password before starting it. Versions that keep the placeholder disable the corresponding admin functions.
3. Upload `main.py` to the Raspberry Pi Pico as `/main.py`. Upload any companion HTML/text files from this archive with their original names.
4. Read the repository's Getting Started and Security notes before deploying: https://github.com/theeskaman/Hive-ChatRoom

Do not commit a copy containing real Wi-Fi or admin credentials. Use on a trusted local network only; do not expose the service directly to the Internet.