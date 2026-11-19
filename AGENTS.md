# AGENTS.md

## Project Overview
Pimoroni Skywriter 3D gesture sensor (MGC3130 / GestIC) driver repository (`v0.0.9`, `library/setup.py`).
Contains the Raspberry Pi Python driver (`library/skywriter/__init__.py`), C++ Arduino library (`arduino/Skywriter/`), Pico W build/flash tooling (`pico-arduino/flash.sh`), GestIC firmware updater (`firmware/`), and Debian packaging (`packaging/`).

## To build

`pico-arduino/` is the folder to contain firmware related to the conversion of the existing Arduino code for Pico and Pico W BLE hardware.
`pico-python/` is the folder to contain firmware related to the conversion of the existing Python code for Pico and Pico W BLE hardware.

## Environment
- Container Python: `Python 3.12.3`; Arduino toolchain: `/home/user/local/bin/arduino-cli`.
- Pico W target (`pico-arduino/flash.sh`): FQBN `rp2040:rp2040:rpipicow:ipbtstack=ipv4btcble` (Earle Philhower core).
  The `ipbtstack=ipv4btcble` suffix is the core's "IPv4 + Bluetooth" build menu: the BTstack (Bluetooth) libraries are not linked without it, so any BLE HID (Bluetooth Low Energy Human Interface Device) sketch — e.g. `pico-arduino/SkywriterController` — fails a plain-FQBN build with "This library needs Bluetooth enabled". `pico-arduino/flash.sh` and `run_tests.sh` pass this option; use it for any manual `arduino-cli compile`. Serial port `/dev/ttyACM*` or `/dev/ttyUSB*` (running USB ID `2e8a:f00a`), BOOTSEL drive `RPI-RP2` (bootloader USB ID `2e8a:0003`). Connect via a direct USB port (unreliable behind hubs).
- Package metadata pins: `X-Python-Version: >= 2.7`, `X-Python3-Version: >= 3.4` (`packaging/debian/control`), `install_requires=['RPi.GPIO']` (`library/setup.py`), `autopy==0.51` (`examples/README.md`).
- System dependencies on Raspberry Pi (`README.md`, `packaging/debian/control`):
  ```bash
  sudo apt install python3-smbus
  sudo raspi-config nonint do_i2c 0
  ```
- Install Python library from source (`README.md` notes `cd skywriter-hat/python/library`, but actual repo path is `library/`):
  ```bash
  cd library && python3 setup.py install
  ```

## Common Tasks
- **Compile & flash Pico W sketch** (`pico-arduino/flash.sh` — compiles to `build/`, resets via 1200-baud touch on serial, waits up to 30s for `RPI-RP2`, mounts via `udisksctl` if needed, copies `.uf2`, and waits 15s for serial return):
  ```bash
  ./pico-arduino/flash.sh path/to/sketch
  ```
- **Compile Pico W sketch only** (`pico-arduino/flash.sh`):
  ```bash
  arduino-cli compile -b rp2040:rp2040:rpipicow:ipbtstack=ipv4btcble --output-dir build path/to/sketch
  ```
- **Install Python dependencies**: `python3 -m pip install skywriter` (`README.md`) or `cd library && python3 setup.py install` (`library/setup.py`).
- **Lint & Full Debian build**: No Python linter or typechecker is configured (`library/skywriter/__init__.py` has `# noqa: E241` comments). Full Debian build + `lintian` + `gpg --verify` (`packaging/makeall.sh`):
  ```bash
  cd packaging && ./makeall.sh
  ```
- **Unit / Smoke test (mocked hardware)**: `cd library && python3 test.py` (`library/test.py` mocks `RPi`, `RPi.GPIO`, and `smbus`, then registers `@skywriter.airwheel()` and `@skywriter.move()`).
- **Hardware interactive test**: `cd examples && sudo ./test.py` (`examples/README.md`, `examples/test.py`).
- **Slow / dangerous operations (avoid in normal loops)**: `firmware/update.py` flashes MGC3130 loader and firmware over I2C with 10s–30s block timeouts and can brick hardware (`firmware/README.md`).

## Data
- **Datasheets & protocol**: Hardware reference PDFs live in `datasheets/Datasheet.pdf` and `datasheets/Interface.pdf`.
- **Firmware payloads**: `firmware/fw.py` holds read-only encrypted GestIC image records (`FW_IV`, `FW_VERSION`, `FW_UPDATE_DATA`, `LDR_IV`, `LDR_VERSION`, `LDR_UPDATE_DATA`). Treat `datasheets/` and `firmware/fw.py` as read-only.
- **Sample sensor packet slice**: `_do_poll()` in `library/skywriter/__init__.py` reads a 26-byte block via `i2c.read_i2c_block_data(0x42, 0x00, 26)` and dispatches `data[3] == 0x91` (`SW_SENSOR_DATA`) to `_handle_sensor_data(data)`.
- **Seeds & offline tests**: `firmware/update.py` fixes `self.session_id = 123` (with `#random.getrandbits(32)` commented out). Keep seeds fixed and mock `RPi.GPIO` and `smbus` (`library/test.py`) with no network or I2C calls in tests.

## Verification
- **Pico W build & flash**: `./pico-arduino/flash.sh path/to/sketch` (exit `0` confirms compile, UF2 flash, and serial port recovery; monitor USB resets with `journalctl -kf | grep -E 'usb|sdb|ttyACM'`).
- **Python library**: `cd library && python3 test.py` (`library/test.py` — requires `mock` and mocked `SMBus` status responses; see Gotchas).
- **Debian packaging**: `cd packaging && ./makeall.sh`.

## Conventions
- **Summarise changes for non-specialists**: Every change summary (commits, reports, status updates) must be written for a reader who does not know electronics jargon. Always spell out acronyms and initialisms on first use — e.g. I2C (Inter-Integrated Circuit, the two-wire bus to the sensor), BLE (Bluetooth Low Energy), HID (Human Interface Device, the standard for mice/keyboards), UF2 (USB Flashing Format), GPIO (General-Purpose Input/Output pins), USB CDC (Communications Device Class, the USB serial port), BOOTSEL (boot select, the Pico's flashing mode). State what changed and why in plain language before any technical detail.
- **Search first**: Reuse existing protocol constants (`SW_*`), payload offsets (`SW_PAYLOAD_*`), and event decorators/callbacks in `library/skywriter/__init__.py` and `arduino/Skywriter/skywriter.h` before writing new code.
- **Pico Arduino sketches**: Each sketch lives in its own folder matching the `.ino` filename. Always use `pico-arduino/flash.sh` (do not run `arduino-cli upload` directly or hard-code `/dev/ttyACM0`), and keep the default CDC USB serial stack enabled so the 1200-baud BOOTSEL reset works.
- **Directories never to modify**: `datasheets/`, `firmware/fw.py`, sketch `build/` directories (written by `pico-arduino/flash.sh`), and generated `library/debian/` or `library/build/` (`packaging/makedeb.sh` deletes and overwrites them).
- **Version bumps**: `packaging/makelog.sh` overwrites `packaging/debian/changelog`, `library/CHANGELOG.txt`, `library/setup.py`, and `library/skywriter/__init__.py` from `packaging/CHANGELOG`.

## Gotchas
- **Do not use `arduino-cli upload` on Pico W**: Its built-in reset and drive scan fail on this host. Use `pico-arduino/flash.sh`, which handles `stty -F <port> 1200`, waits for udisks auto-mount (~2s after attach) or runs `udisksctl mount -b`, and copies the UF2.
- **Normal `dmesg` errors during UF2 copy**: The RP2040 reboots immediately on the last UF2 block; `device offline error` or `FAT-fs ... unable to read boot sector` in `dmesg` and `sync` failures are normal. If `RPI-RP2` never appears, hold BOOTSEL while plugging in and rerun `pico-arduino/flash.sh`. If it returns as `RP2 Boot` (`0003`) instead of `Pico W` (`f00a`), verify `build/*.uf2` is non-empty and starts with `55 46 32 0a` (`UF2\n`).
- **`library/test.py` fails on import without patching**: It imports external `mock` (not in Python 3.12 stdlib unless `unittest.mock` is aliased) and `@skywriter.airwheel()` calls `setup()`, which loops 10x in `get_status(0xA2)` checking `data[3] == 0x15` (`RuntimeError` on unconfigured `Mock()`).
- **Infinite background thread on setup**: `skywriter.setup()` starts a daemon `AsyncWorker` polling thread (`_start_poll()`). Call `skywriter._stop_poll()` to stop it cleanly.
- **Arduino `poll()` & Python `_on_airwheel` quirks**: `_SkyWriter::begin()` in `arduino/Skywriter/skywriter.cpp` does not send `SW_SET_RUNTIME` (`0xA2`) config commands (sensor configuration belongs to the P3.16 firmware). In `library/skywriter/__init__.py`, `_on_airwheel` is initialized to `[]` (line 96) and checked with `callable(_on_airwheel)` (line 344). Updated 2026-11-17 (P3.23): the old second gotcha — `poll()` releasing the transfer pin as plain `INPUT` instead of `INPUT_PULLUP` — is FIXED; every `poll()` exit path now releases the transfer (TS) line with its pull-up restored, and `poll()` additionally exposes public health counters (`polls`, `ts_low_polls`, `short_reads`, frame counts by message type, P3.22). Updated 2026-11-18 (P4.0a H7): the first hardware capture of those counters shows `other` frames at 100 % of polls from boot with `short_reads=0` — the leading suspect is poll()'s single 132-byte I2C (Inter-Integrated Circuit) request over-reading past the 26-byte sensor frame and desynchronising the message framing. Open items P3.24 (unknown-frame content snapshot) and P3.25 (port the Python driver's Size-field-sized reads to the Arduino driver) address this; do not trust `frames other` counts on builds older than P3.25. Updated 2026-11-19 (P3.24 + P3.25): both landed — `poll()` now reads EXACTLY 26 bytes first and fetches continuation reads only when the frame's own Size field (validated 4..132) says the message is longer (26 + 32-byte chunks, the Python driver's P3.11c pattern); the 132-byte over-read is gone, and incomplete or corrupt-Size frames are never dispatched half-read. `frames_other` now counts every transfer that read a header but did not dispatch (unknown identity, corrupt Size, or an incomplete frame), and the driver stores the last such frame's first 8 bytes + the byte count the reads actually returned as public state (`other_snapshot` / `other_snapshot_read`) which the health line prints as `other_snap=` / `other_read=` — the instrument the next hardware session reads to confirm or refute H7 (a shifted 0x91 = misalignment; all 0x00 = padding on empty reads; all 0xFF = a wedged slave). Whether the real sensor continues its I2C buffer across the separate reads of one asserted transfer is the remaining P4.1 hardware question.
