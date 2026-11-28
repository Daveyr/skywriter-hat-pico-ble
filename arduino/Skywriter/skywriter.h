#include <Wire.h>

#ifndef _SKYWRITER_H
#define _SKYWRITER_H

#define SW_ADDR 0x42

#define SW_HEADER_SIZE   4

#define SW_DATA_DSP      1 //0b0000000000000001
#define SW_DATA_GESTURE  1 << 1 //0b0000000000000010
#define SW_DATA_TOUCH    1 << 2 //0b0000000000000100
#define SW_DATA_AIRWHEEL 1 << 3 //0b0000000000001000
#define SW_DATA_XYZ      1 << 4 //0b0000000000010000

#define SW_SYSTEM_STATUS 0x15
#define SW_REQUEST_MSG   0x06
#define SW_FW_VERSION    0x83
#define SW_SET_RUNTIME   0xA2
#define SW_SENSOR_DATA   0x91

#define SW_PAYLOAD_HDR_CONFIGMASK  0 // 2 Bytes
#define SW_PAYLOAD_HDR_TS          2 // 1 Byte
#define SW_PAYLOAD_HDR_SYSINFO     3 // 1 Byte
#define SW_PAYLOAD_DSP_STATUS      4
#define SW_PAYLOAD_GESTURE         6  // 4 Bytes
#define SW_PAYLOAD_TOUCH           10 // 4 Bytes
#define SW_PAYLOAD_AIRWHEEL        14 // 2 Bytes
#define SW_PAYLOAD_X               16 // 2 bytes
#define SW_PAYLOAD_Y               18 // 2 bytes
#define SW_PAYLOAD_Z               20 // 2 bytes

#define SW_SYS_POSITION            1
#define SW_SYS_AIRWHEEL            1 << 1

/*
  Control-frame receive formats (fix item P3.11b, deviation D9).
  System_Status (0x15) — Interface.pdf §4.1, example §3.6 Table 3-8:
    payload byte 0 = MsgID acknowledged (e.g. Set_Runtime_Parameter 0xA2),
    byte 1 = MaxCmdSize (informational), bytes 2-3 = ErrorCode little-endian
    ("0" = the command was applied correctly).
  Fw_Version_Info (0x83) — Interface.pdf §4.3 Table 4-5:
    payload byte 0 = FwValid (only 0xAA = valid GestIC Library, Table 4-6),
    bytes 8..127 = FwVersion, a 120-byte ASCII field, NUL-padded.
  Read pattern (fix item P3.25, hypothesis H7): the first read of a transfer
  asks for exactly the classic full-layout sensor frame; a longer message
  (its own Size field says so) is fetched with continuation reads bounded
  by that Size — NEVER one large request over-reading past the message end
  (the former 132-byte request desynchronised the sensor's message framing;
  see poll()). So one transfer reads a whole frame, never more.
*/
#define SW_MAX_FRAME_SIZE          132 // header 4 + payload 128 (Fw_Version_Info)
#define SW_FIRST_READ_SIZE         26  // the classic full-layout sensor frame
#define SW_I2C_READ_CHUNK          32  // continuation chunk, bounded by the frame's Size
#define SW_PAYLOAD_SYSTEM_STATUS_ID    0 // 1 byte
#define SW_PAYLOAD_SYSTEM_STATUS_ERROR 2 // 2 bytes, little-endian
#define SW_PAYLOAD_FW_INFO_VALID       0 // 1 byte: only 0xAA is valid (Table 4-6)
#define SW_PAYLOAD_FW_INFO_VERSION     8 // 120 bytes, ASCII, NUL-padded
#define SW_FW_VERSION_FIELD_SIZE   120

/*
  Constants for identifying tap
*/
#define SW_DOUBLETAP_CENTER        0
#define SW_DOUBLETAP_EAST          1
#define SW_DOUBLETAP_NORTH         2
#define SW_DOUBLETAP_WEST          3
#define SW_DOUBLETAP_SOUTH         4
#define SW_TAP_CENTER              5
#define SW_TAP_EAST                6
#define SW_TAP_NORTH               7
#define SW_TAP_WEST                8
#define SW_TAP_SOUTH               9
#define SW_TOUCH_CENTER            10
#define SW_TOUCH_EAST              11
#define SW_TOUCH_NORTH             12
#define SW_TOUCH_WEST              13
#define SW_TOUCH_SOUTH             14

#define SW_GESTURE_GARBAGE         1
#define SW_FLICK_WEST_EAST         2
#define SW_FLICK_EAST_WEST         3
#define SW_FLICK_SOUTH_NORTH       4
#define SW_FLICK_NORTH_SOUTH       5
#define SW_CIRCLE_CLOCKWISE        6
#define SW_CIRCLE_CCLOCKWISE       7

class _SkyWriter 
{
  public:
    void begin(unsigned char pin_xfer, unsigned char pin_reset);
    void poll();
    void onTouch( void (*)(unsigned char) );
    void onAirwheel( void (*)(float) );
    void onGesture( void (*)(unsigned char) );
    void onXYZ( void (*)(unsigned int, unsigned int, unsigned int) );
    // Optional control-frame callbacks (fix item P3.11b): every System_Status
    // acknowledge reports (msg_id, error); every *valid* Fw_Version_Info
    // report (FwValid 0xAA) reports (fw_valid, nul-stripped version string).
    // The C++ counterpart of the Python driver's `system_status()` /
    // `fw_version()` decorators.
    void onSystemStatus( void (*)(unsigned char, unsigned int) );
    void onFirmwareVersion( void (*)(unsigned char, const char*) );
    unsigned char last_gesture, last_touch;
    // Attributes of the last recognized gesture, decoded from the full
    // 32-bit GestureInfo word (Interface.pdf §4.5, Table 4-10) — the C++
    // counterparts of the Python driver's `gesture_class` / `gesture_edge`
    // globals (fix item P3.11). Handlers read them alongside `last_gesture`
    // exactly like the Python driver's module state. Deviation D7: the old
    // code kept only `last_gesture` (GestureInfo byte 0) and discarded
    // these.
    unsigned char last_gesture_class;  // bits 12-15: 0 garbage, 1 flick, 2 circle
    bool last_gesture_edge;            // bit 16: edge-flick flag
    unsigned int  x, y, z;
    // Health counters (fix item P3.22, hardware gate P4.0a T5): public
    // state like `last_gesture`, so any sketch (and the serial probe) can
    // read them without touching the driver's API. They only ever
    // increment — the driver itself never prints.
    //   polls            — every poll() call (the loop calls it at 200 Hz).
    //   ts_low_polls     — polls where the sensor's data-ready (transfer,
    //                      TS) line read LOW, i.e. a transfer started.
    //   short_reads      — transfers whose I2C read returned fewer than
    //                      the 4 header bytes (the H1 failed-read path;
    //                      with P3.23's fix that path releases the line).
    //   frames_sensor_data / frames_status / frames_firmware
    //                    — complete frames dispatched, by message identity
    //                      (0x91 sensor data, 0x15 System_Status ack,
    //                      0x83 Fw_Version_Info).
    //   frames_other     — transfers that read a header but did NOT
    //                      dispatch (fix items P3.24/P3.25): an unknown
    //                      message identity, a Size field outside
    //                      4..SW_MAX_FRAME_SIZE, or a frame whose
    //                      continuation reads could not complete it. The
    //                      health line's shares close over these: every
    //                      transfer is short + sensor + status + fw +
    //                      other. (Before P3.25 this counted only the
    //                      unknown-identity dispatch case.)
    //   other_snapshot[8] / other_snapshot_read
    //                    — fix item P3.24, the instrument for the
    //                      hardware gate P4.0a: the first 8 bytes (size,
    //                      flags, sequence, identity + 4 payload bytes)
    //                      and the byte count the reads actually returned
    //                      of the LAST undispatched frame. poll() only
    //                      stores; the sketch's health line prints it.
    //                      Content signatures that name the fault: a 0x91
    //                      identity visible at a SHIFTED offset = the
    //                      sensor's message framing is misaligned (H7);
    //                      all 0x00 = the bus answers padding on reads
    //                      with nothing queued; all 0xFF = a wedged
    //                      slave. A known identity with a read count under
    //                      the promised Size = an incomplete read.
    unsigned long polls = 0;
    unsigned long ts_low_polls = 0;
    unsigned long short_reads = 0;
    unsigned long frames_sensor_data = 0;
    unsigned long frames_status = 0;
    unsigned long frames_firmware = 0;
    unsigned long frames_other = 0;
    // Latest undispatched-frame snapshot (P3.24); zero until the first
    // such frame. `other_snapshot_read` counts the bytes the reads
    // actually returned (the requestFrom counts the old code ignored).
    unsigned char other_snapshot[8] = {0,0,0,0,0,0,0,0};
    unsigned char other_snapshot_read = 0;
    // Accumulated AirWheel rotation in degrees (clamped 0..1000, mirroring
    // the Python driver's `rotation` global — the P3.4 reference).
    float rotation = 0.0f;
  private:
    void (*handle_touch)(unsigned char)   = NULL;
    void (*handle_airwheel)(float)    = NULL;
    void (*handle_gesture)(unsigned char) = NULL;
    void (*handle_xyz)(unsigned int, unsigned int, unsigned int);
    void (*handle_system_status)(unsigned char, unsigned int) = NULL;
    void (*handle_firmware_version)(unsigned char, const char*) = NULL;
    // AirWheel counter reference: `airwheel_counter_valid` stands in for the
    // Python driver's `_lastrotation = None` sentinel — false until a frame
    // with valid AirWheel data establishes the baseline, and cleared again by
    // any frame without valid AirWheel data (see handles_sensor_data).
    unsigned char lastrotation = 0;
    bool airwheel_counter_valid = false;
    unsigned char xfer, rst, addr;
    // Frame receiving buffer: sized for the longest sensor message,
    // Fw_Version_Info (0x83, 132 bytes = 4 header + 128 payload), so a
    // whole frame always fits. Since P3.25 the frame arrives as a 26-byte
    // first read plus Size-bounded continuation reads (never one large
    // over-reading request); the payload copy is bounded by the frame's
    // own Size field, so bus padding or over-answering never reaches a
    // decoder (the same rule as the Python driver, P3.11c).
    unsigned char command_buffer[SW_MAX_FRAME_SIZE];
    // P3.24: count + snapshot one transfer that read a header but will not
    // dispatch (unknown identity, corrupt Size, or incomplete frame).
    // `payload_avail` bytes of the payload already sit in command_buffer;
    // the snapshot zero-fills the rest of its 4 payload slots.
    void record_undispatched_frame(unsigned char d_size, unsigned char d_flags,
                                  unsigned char d_seq, unsigned char d_ident,
                                  unsigned char read_count,
                                  unsigned char payload_avail);
    void handle_sensor_data(unsigned char* data);
    void handle_status_info(unsigned char* data);
    void handle_firmware_info(unsigned char* data);
};

namespace { _SkyWriter Skywriter; }

#endif
