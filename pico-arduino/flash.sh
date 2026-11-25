#!/bin/sh
# flash.sh — usage: ./flash.sh [sketch-dir]
# Compiles the sketch and flashes it whether the Pico W is running (serial port
# present) or already in BOOTSEL mode (only the RPI-RP2 drive present).
#
# Optional build knobs (environment variables):
#   SKYWRITER_EVENT_TRACE=1  build the per-event evidence trace in
#                            (fix item P3.29): one compact SKYTRACE serial
#                            line per dispatched sensor event, for the
#                            acceptance-run builds. Off by default so the
#                            200 Hz position path keeps the console quiet.
set -eu

FQBN=rp2040:rp2040:rpipicow:ipbtstack=ipv4btcble
# `ipbtstack=ipv4btcble` = the core's "IPv4 + Bluetooth" build option: without
# it the BTstack (Bluetooth) libraries are not linked and any BLE (Bluetooth
# Low Energy) HID sketch fails with "This library needs Bluetooth enabled".
DRIVE_LABEL=RPI-RP2
BUILD_DIR=build

# P3.29: forward the acceptance-run trace switch as a compiler definition
# (the sketch's `#ifndef SKYWRITER_EVENT_TRACE` fallback keeps normal builds
# untouched). `--build-property build.extra_flags=-D…` is the arduino-cli
# 1.x way to add a define (this CLI version has no --build-flags flag).
# BUILD_PROPERTY is deliberately left unquoted at the call site: POSIX sh
# has no arrays, and the value word-splits into exactly the two arguments
# wanted (`--build-property` + a value with no spaces in it).
BUILD_PROPERTY=""
if [ "${SKYWRITER_EVENT_TRACE:-0}" = "1" ]; then
  BUILD_PROPERTY='--build-property build.extra_flags=-DSKYWRITER_EVENT_TRACE=1'
fi

find_port() {
  arduino-cli board list | awk '/\/dev\/tty(ACM|USB)/ {print $1; exit}'
}

cd "${1:-.}"

arduino-cli compile -b "$FQBN" $BUILD_PROPERTY --output-dir "$BUILD_DIR" .

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
