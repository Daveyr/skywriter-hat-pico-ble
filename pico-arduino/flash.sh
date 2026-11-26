#!/bin/sh
# flash.sh — usage: ./flash.sh [sketch-dir]
# Compiles the sketch and flashes it whether the Pico W is running (serial port
# present) or already in BOOTSEL mode (only the RPI-RP2 drive present).
#
# Optional build knobs (environment variables):
#   SKYWRITER_EVENT_TRACE=1       build the per-event evidence trace in
#                                 (fix item P3.29): one compact SKYTRACE
#                                 serial line per dispatched sensor event,
#                                 for the acceptance-run builds. Off by
#                                 default so the 200 Hz position path keeps
#                                 the console quiet.
#   SKYWRITER_CAL_DISABLE=1       build the genuine auto-calibration-DISABLE
#                                 experiment (fix item P3.31): the fourth
#                                 sensor-configuration command sends
#                                 Argument0 = 0x1F, mask = 0x1F — all five
#                                 auto-calibration features OFF (the legacy
#                                 payload the default build sends actually
#                                 leaves them all ON; see the sketch's
#                                 command-4 comment). The serial lines name
#                                 the variant as cal=disable_all.
#   SKYWRITER_CAL_DISABLE_IDLE=1  the fallback experiment: only idle
#                                 calibration off (Argument0 bit 3, mask bit
#                                 3), cal=disable_idle on the serial lines.
#                                 Ignored when SKYWRITER_CAL_DISABLE=1.
# The knobs may combine — the acceptance experiment build is
#   SKYWRITER_EVENT_TRACE=1 SKYWRITER_CAL_DISABLE=1 ./flash.sh …
set -eu

FQBN=rp2040:rp2040:rpipicow:ipbtstack=ipv4btcble
# `ipbtstack=ipv4btcble` = the core's "IPv4 + Bluetooth" build option: without
# it the BTstack (Bluetooth) libraries are not linked and any BLE (Bluetooth
# Low Energy) HID sketch fails with "This library needs Bluetooth enabled".
DRIVE_LABEL=RPI-RP2
BUILD_DIR=build

# The sketch-dir argument is saved BEFORE the positional parameters are
# reused as the compile-argument scratch space below.
SKETCH_DIR_ARG=${1:-.}

# P3.29 + P3.31: forward the requested build switches to the compiler. All
# requested -D definitions accumulate into ONE `compiler.cpp.extra_flags`
# value. TWO arduino-cli 1.x behaviours shaped this (both verified
# 2026-11-26):
#   * repeated --build-property flags for the SAME key are last-one-wins
#     (two flags each defining one macro left the first macro undefined),
#     so the trace and experiment switches can only combine as one
#     space-separated value;
#   * `build.extra_flags` is the BOARD'S OWN flag slot — boards.txt gives
#     the Pico W `-DPICO_CYW43_SUPPORTED=1` through it, and overriding
#     that slot with our -D flags makes the core compile WITHOUT the
#     WiFi/Bluetooth driver while arduino-cli caches that broken core
#     archive per FQBN (every later build of that FQBN then fails with
#     `undefined reference to init_cyw43_wifi` until
#     ~/.cache/arduino/cores/<fqbn> is deleted). `compiler.cpp.extra_flags`
#     is the empty compiler-level slot: it ADDS our flags without
#     touching the board's.
# POSIX sh has no arrays, so the argument list is built in the positional
# parameters: `"$@"` keeps `--build-property` and its space-containing
# value as exactly two arguments.
set --
if [ "${SKYWRITER_EVENT_TRACE:-0}" = "1" ]; then
  set -- "$@" -DSKYWRITER_EVENT_TRACE=1
fi
if [ "${SKYWRITER_CAL_DISABLE:-0}" = "1" ]; then
  set -- "$@" -DSKYWRITER_CAL_DISABLE=1
elif [ "${SKYWRITER_CAL_DISABLE_IDLE:-0}" = "1" ]; then
  set -- "$@" -DSKYWRITER_CAL_DISABLE_IDLE=1
fi
if [ "$#" -gt 0 ]; then
  FOLDED_FLAGS=""
  for definition in "$@"; do
    FOLDED_FLAGS="$FOLDED_FLAGS $definition"
  done
  set -- --build-property "compiler.cpp.extra_flags=${FOLDED_FLAGS# }"
fi

find_port() {
  arduino-cli board list | awk '/\/dev\/tty(ACM|USB)/ {print $1; exit}'
}

cd "$SKETCH_DIR_ARG"

arduino-cli compile -b "$FQBN" "$@" --output-dir "$BUILD_DIR" .

PORT=$(find_port)
if [ -n "$PORT" ]; then
  # Opening at 1200 baud reboots the Pico into BOOTSEL; the port vanishes, so stty may report an error.
  stty -F "$PORT" 1200 2>/dev/null || true
fi

i=0
until [ -e "/dev/disk/by-label/$DRIVE_LABEL" ]; do
  i=$((i + 1))
  if [ "$i" -gt 30 ]; then
    echo "no $DRIVE_LABEL drive after 30s; hold BOOTSEL while plugging in and rerun" >&2
    exit 1
  fi
  sleep 1
done

DEV=$(readlink -f "/dev/disk/by-label/$DRIVE_LABEL")

i=0
MNT=$(findmnt -n -o TARGET -S "$DEV" || true)
while [ -z "$MNT" ]; do
  i=$((i + 1))
  if [ "$i" -gt 15 ]; then
    echo "could not mount $DEV" >&2
    exit 1
  fi
  if [ "$i" -eq 5 ]; then
    udisksctl mount -b "$DEV" >/dev/null || true
  fi
  sleep 1
  MNT=$(findmnt -n -o TARGET -S "$DEV" || true)
done

set -- "$BUILD_DIR"/*.uf2
cp "$1" "$MNT/"
# The Pico resets as soon as the last UF2 block lands, so sync can fail harmlessly.
sync || true

i=0
until [ -n "$(find_port)" ]; do
  i=$((i + 1))
  if [ "$i" -gt 15 ]; then
    echo "flashed, but no serial port came back; check the board" >&2
    exit 1
  fi
  sleep 1
done
echo "flashed $1 via $MNT"
