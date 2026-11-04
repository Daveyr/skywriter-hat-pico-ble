#!/bin/sh
# flash.sh — usage: ./flash.sh [sketch-dir]
# Compiles the sketch and flashes it whether the Pico W is running (serial port
# present) or already in BOOTSEL mode (only the RPI-RP2 drive present).
set -eu

FQBN=rp2040:rp2040:rpipicow
DRIVE_LABEL=RPI-RP2
BUILD_DIR=build

find_port() {
  arduino-cli board list | awk '/\/dev\/tty(ACM|USB)/ {print $1; exit}'
}

cd "${1:-.}"

arduino-cli compile -b "$FQBN" --output-dir "$BUILD_DIR" .

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
