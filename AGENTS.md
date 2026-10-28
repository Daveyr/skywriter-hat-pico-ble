# AGENTS.md

## Project Overview
Pimoroni Skywriter 3D gesture sensor (MGC3130 / GestIC) driver repository (`v0.0.9`, `library/setup.py`).
Contains the Raspberry Pi Python driver (`library/skywriter/__init__.py`), C++ Arduino library (`arduino/Skywriter/`), Pico W build/flash tooling (`pico-arduino/flash.sh`), GestIC firmware updater (`firmware/`), and Debian packaging (`packaging/`).
Currently on branch `pico-ble`; `specs/` is an empty directory for upcoming Pico BLE work.

## Environment
- Container Python: `Python 3.12.3`; Arduino toolchain: `/home/user/local/bin/arduino-cli`.
- Pico W target (`pico-arduino/flash.sh`): FQBN `rp2040:rp2040:rpipicow` (Earle Philhower core), serial `/dev/ttyACM*` or `/dev/ttyUSB*` (running USB ID `2e8a:f00a`), BOOTSEL drive `RPI-RP2` (bootloader USB ID `2e8a:0003`). Connect via a direct USB port (unreliable behind hubs).
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
  arduino-cli compile -b rp2040:rp2040:rpipicow --output-dir build path/to/sketch
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
- **Search first**: Reuse existing protocol constants (`SW_*`), payload offsets (`SW_PAYLOAD_*`), and event decorators/callbacks in `library/skywriter/__init__.py` and `arduino/Skywriter/skywriter.h` before writing new code.
- **Pico Arduino sketches**: Each sketch lives in its own folder matching the `.ino` filename. Always use `pico-arduino/flash.sh` (do not run `arduino-cli upload` directly or hard-code `/dev/ttyACM0`), and keep the default CDC USB serial stack enabled so the 1200-baud BOOTSEL reset works.
- **Directories never to modify**: `datasheets/`, `firmware/fw.py`, sketch `build/` directories (written by `pico-arduino/flash.sh`), and generated `library/debian/` or `library/build/` (`packaging/makedeb.sh` deletes and overwrites them).
- **Version bumps**: `packaging/makelog.sh` overwrites `packaging/debian/changelog`, `library/CHANGELOG.txt`, `library/setup.py`, and `library/skywriter/__init__.py` from `packaging/CHANGELOG`.

## Gotchas
- **Do not use `arduino-cli upload` on Pico W**: Its built-in reset and drive scan fail on this host. Use `pico-arduino/flash.sh`, which handles `stty -F <port> 1200`, waits for udisks auto-mount (~2s after attach) or runs `udisksctl mount -b`, and copies the UF2.
- **Normal `dmesg` errors during UF2 copy**: The RP2040 reboots immediately on the last UF2 block; `device offline error` or `FAT-fs ... unable to read boot sector` in `dmesg` and `sync` failures are normal. If `RPI-RP2` never appears, hold BOOTSEL while plugging in and rerun `pico-arduino/flash.sh`. If it returns as `RP2 Boot` (`0003`) instead of `Pico W` (`f00a`), verify `build/*.uf2` is non-empty and starts with `55 46 32 0a` (`UF2\n`).
- **`library/test.py` fails on import without patching**: It imports external `mock` (not in Python 3.12 stdlib unless `unittest.mock` is aliased) and `@skywriter.airwheel()` calls `setup()`, which loops 10x in `get_status(0xA2)` checking `data[3] == 0x15` (`RuntimeError` on unconfigured `Mock()`).
- **Infinite background thread on setup**: `skywriter.setup()` starts a daemon `AsyncWorker` polling thread (`_start_poll()`). Call `skywriter._stop_poll()` to stop it cleanly.
- **Arduino `poll()` & Python `_on_airwheel` quirks**: `_SkyWriter::begin()` in `arduino/Skywriter/skywriter.cpp` does not send `SW_SET_RUNTIME` (`0xA2`) config commands and `poll()` resets `xfer` to `INPUT` instead of `INPUT_PULLUP`. In `library/skywriter/__init__.py`, `_on_airwheel` is initialized to `[]` (line 62) and checked with `callable(_on_airwheel)` (line 255).
