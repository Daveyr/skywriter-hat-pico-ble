#include "skywriter.h"
#include <Arduino.h>

void _SkyWriter::begin(unsigned char pin_xfer, unsigned char pin_reset){
  this->xfer = pin_xfer;
  this->rst  = pin_reset;
  this->addr = SW_ADDR;
  
  Wire.begin();
  
  pinMode(this->xfer, INPUT_PULLUP);
  pinMode(this->rst,  OUTPUT);
  digitalWrite(this->rst, LOW);
  delay(10);
  digitalWrite(this->rst, HIGH);
  delay(50);
}

void _SkyWriter::poll(){
  // Health counters (fix item P3.22, hardware P4.0a T5): public state, like
  // `last_gesture`, so any sketch can read them. polls counts EVERY call;
  // ts_low_polls counts the calls where the sensor's data-ready (transfer,
  // TS) line was low, i.e. an actual transfer started; short_reads counts
  // the transfers whose read returned fewer than the 4 header bytes (the
  // H1 failed-read path). The 200 Hz hot path only increments; it never
  // prints.
  this->polls++;
  if (!digitalRead(this->xfer)){
    this->ts_low_polls++;
    pinMode(this->xfer, OUTPUT);
    digitalWrite(this->xfer, LOW);
    
    // Size-field reads (fix item P3.25, hypothesis H7): the first read
    // asks for EXACTLY the classic full-layout sensor frame, and only a
    // message the frame's own Size field announces as longer is fetched
    // with continuation reads bounded by that Size — the Python driver's
    // P3.11c pattern (26 first, then 32-byte chunks). The former single
    // 132-byte request (P3.11b) clocked up to 106 bytes past the end of
    // every 26-byte frame; what the sensor serves there is undefined, and
    // the first hardware counter capture (other=100 % from the first
    // poll, zero events, HW session 4) is exactly the desynchronised
    // framing that over-read produces. The 132-byte Fw_Version_Info
    // capture still works: its Size field drives the continuations.
    unsigned char got = Wire.requestFrom(this->addr, (unsigned char)SW_FIRST_READ_SIZE);
    
    unsigned char d_size,d_flags,d_seq,d_ident;
    
    if( got >= SW_HEADER_SIZE ){
      d_size  = Wire.read();
      d_flags = Wire.read();
      d_seq   = Wire.read();
      d_ident = Wire.read();
    }
    else{
      // Failed read (fix item P3.23, hypothesis H1): fewer than the 4
      // header bytes arrived. The early return used to leave the transfer
      // line driven LOW — the sensor's data buffers stay pinned, nothing
      // new ever arrives, and the controller looks alive while producing
      // no input at all (hardware session 3's symptom, P4.0a). Release on
      // every exit path now, exactly as the Python driver's try/finally
      // has done since P3.11d.
      this->short_reads++;
      digitalWrite(this->xfer, HIGH);
      pinMode(this->xfer, INPUT_PULLUP);
      return;
    }

    // The byte count the reads actually returned (fix item P3.24): the
    // requestFrom count the old code ignored — the evidence number the
    // undispatched-frame snapshot prints against the promised Size.
    unsigned char read_count = got;
    
    this->command_buffer[0] = '\0';
    
    // The Size field counts the whole message INCLUDING this 4-byte
    // header (Interface.pdf §3.3; §2.3 note 1 recommends sizing the read
    // from it). A value outside 4..SW_MAX_FRAME_SIZE cannot describe a
    // real message: no continuation read, no dispatch — the frame is
    // counted and snapshotted below instead of decoded half-read.
    if( d_size >= SW_HEADER_SIZE && d_size <= SW_MAX_FRAME_SIZE ){
      // Copy the payload bytes that arrived with the first read. Bounded
      // by the frame's own Size field: an over-answering read (bus
      // padding past the message end) never spills into the payload —
      // the same rule as the Python driver's sized reads (P3.11c), and
      // the bound that keeps the copy inside the receive buffer.
      unsigned char received = SW_HEADER_SIZE;
      while( Wire.available() && received < d_size ){
        this->command_buffer[received - SW_HEADER_SIZE] = Wire.read();
        received++;
      }
      
      // Continuation reads, bounded by the Size field, while the transfer
      // line is still asserted — only for messages longer than the first
      // read. A continuation that serves nothing means the frame cannot
      // be completed: stop and dispatch nothing half-read (the Python
      // driver's empty-continuation rule, P3.11c).
      while( received < d_size ){
        unsigned char want = d_size - received;
        if( want > SW_I2C_READ_CHUNK ) want = SW_I2C_READ_CHUNK;
        unsigned char more = Wire.requestFrom(this->addr, want);
        read_count += more;
        if( more == 0 ) break;
        while( Wire.available() && received < d_size ){
          this->command_buffer[received - SW_HEADER_SIZE] = Wire.read();
          received++;
        }
      }
      
      if( received >= d_size ){
        // Complete frame: the payload copy is exactly the Size-field byte
        // range minus the 4-byte header (the P3.3 off-by-four contract),
        // and the terminator stays inside the receive buffer (d_size is
        // validated against SW_MAX_FRAME_SIZE above).
        this->command_buffer[d_size - SW_HEADER_SIZE] = '\0';
      
        switch(d_ident){
          case 0x91:
            this->frames_sensor_data++;
            this->handle_sensor_data(this->command_buffer);
            break;
          case 0x15:
            // System_Status acknowledge, decoded as a control event (P3.11b).
            this->frames_status++;
            this->handle_status_info(this->command_buffer);
            break;
          case 0x83:
            // Fw_Version_Info report, decoded as a control event (P3.11b).
            this->frames_firmware++;
            this->handle_firmware_info(this->command_buffer);
            break;
          default:
            // An unknown message identity: counted and its content
            // snapshotted (fix item P3.24, the P4.0a instrument).
            this->record_undispatched_frame(d_size, d_flags, d_seq, d_ident,
                                            read_count,
                                            d_size - SW_HEADER_SIZE);
            break;
        }
      }
      else{
        // The frame could not be completed up to its Size: dispatch
        // nothing half-read, count it, and snapshot it — the snapshot's
        // read count against the promised Size is the evidence.
        this->record_undispatched_frame(d_size, d_flags, d_seq, d_ident,
                                        read_count,
                                        received - SW_HEADER_SIZE);
      }
    }
    else{
      // Corrupt Size field (under 4 or above the longest real message):
      // no continuation read, no dispatch. Keep at most the snapshot's
      // four payload bytes of what the bus actually served, so the
      // evidence records real content — then count + snapshot.
      unsigned char snap_payload = 0;
      while( Wire.available() && snap_payload < 4 ){
        this->command_buffer[snap_payload++] = Wire.read();
      }
      this->record_undispatched_frame(d_size, d_flags, d_seq, d_ident,
                                      read_count, snap_payload);
    }
    
    // Drain whatever the Size-bounded copies left in the receive buffer
    // (an over-answering read can leave up to a chunk there): the next
    // requestFrom then starts from a clean buffer on every Wire
    // implementation, not only the ones that reset it themselves.
    while( Wire.available() ) Wire.read();
    
    // Release the transfer line after a completed transfer (fix item
    // P3.23, hypothesis H2): the pull-up is RESTORED on release, exactly
    // as the Python driver releases (GPIO.IN with PUD_UP) — a loose or
    // disconnected TS wire must read consistently high, not at random
    // (this reopens and settles the P3.19 pin-mode decision: the old
    // plain-INPUT release is now INPUT_PULLUP on every exit path).
    digitalWrite(this->xfer, HIGH);
    pinMode(this->xfer, INPUT_PULLUP);
  }
}

void _SkyWriter::record_undispatched_frame(unsigned char d_size,
                                          unsigned char d_flags,
                                          unsigned char d_seq,
                                          unsigned char d_ident,
                                          unsigned char read_count,
                                          unsigned char payload_avail){
  // Fix item P3.24 — the instrument that names WHAT the frames the
  // counters cannot decode contain (the hardware gate P4.0a's evidence).
  // Every transfer that read a header but did NOT dispatch — an unknown
  // message identity, a corrupt Size field, or a frame whose continuation
  // reads could not complete it — is counted here, and its first 8 bytes
  // (size, flags, sequence, identity + 4 payload bytes) plus the byte
  // count the reads actually returned are stored as public state. The
  // sketch's health line prints them; the 200 Hz path itself never
  // prints. Content signatures the snapshot separates (P4.0a): a 0x91
  // identity visible at a shifted offset = the sensor's message framing
  // is misaligned (H7); all 0x00 = the bus answers padding on reads with
  // nothing queued; all 0xFF = a wedged slave; a known identity with the
  // read count under the promised Size = an incomplete read.
  // `payload_avail` payload bytes already sit at the front of
  // command_buffer; the rest of the snapshot's payload slots zero-fill.
  this->frames_other++;
  this->other_snapshot[0] = d_size;
  this->other_snapshot[1] = d_flags;
  this->other_snapshot[2] = d_seq;
  this->other_snapshot[3] = d_ident;
  for( unsigned char j = 0; j < 4; j++ ){
    this->other_snapshot[SW_HEADER_SIZE + j] =
      (j < payload_avail) ? this->command_buffer[j] : 0;
  }
  this->other_snapshot_read = read_count;
}

void _SkyWriter::onTouch(    void (*function)(unsigned char) ){this->handle_touch    = function;}
void _SkyWriter::onAirwheel( void (*function)(float)          ){this->handle_airwheel = function;}
void _SkyWriter::onGesture(  void (*function)(unsigned char) ){this->handle_gesture  = function;}
void _SkyWriter::onXYZ(      void (*function)(unsigned int,unsigned int,unsigned int) ){this->handle_xyz  = function;}
void _SkyWriter::onSystemStatus( void (*function)(unsigned char, unsigned int) ){this->handle_system_status = function;}
void _SkyWriter::onFirmwareVersion( void (*function)(unsigned char, const char*) ){this->handle_firmware_version = function;}

void _SkyWriter::handle_status_info(unsigned char* data){
  // System_Status (0x15) — Interface.pdf §4.1, example in §3.6 Table 3-8:
  // payload byte 0 = MsgID acknowledged (e.g. Set_Runtime_Parameter 0xA2 =
  // 170), byte 1 = MaxCmdSize (informational), bytes 2-3 = ErrorCode
  // little-endian ("0" = the message was applied correctly). Mirrors the
  // Python driver's `_handle_status_info`.
  if( this->handle_system_status == NULL ) return;

  this->handle_system_status(
    data[SW_PAYLOAD_SYSTEM_STATUS_ID],
    (unsigned int)( data[SW_PAYLOAD_SYSTEM_STATUS_ERROR + 1] << 8
                  | data[SW_PAYLOAD_SYSTEM_STATUS_ERROR] )
  );
}

void _SkyWriter::handle_firmware_info(unsigned char* data){
  // Fw_Version_Info (0x83) — Interface.pdf §4.3, Table 4-5/4-6: payload
  // byte 0 = FwValid; only an exact 0xAA is a valid GestIC Library (the
  // D6 rule; the Python driver raises for every other value and emits no
  // event, so emitting only here keeps both drivers' event streams in
  // parity). The FwVersion field is payload bytes 8..127, ASCII,
  // NUL-padded; the callback receives it NUL-stripped, exactly what the
  // canonical-record grammar expects.
  if( data[SW_PAYLOAD_FW_INFO_VALID] != 0xAA ) return;

  char version[SW_FW_VERSION_FIELD_SIZE + 1];
  unsigned char j;
  // Copy until the field's own length, stopping either at the NUL padding
  // or at the receive-buffer terminator (where the frame ended).
  for( j = 0; j < SW_FW_VERSION_FIELD_SIZE
              && data[SW_PAYLOAD_FW_INFO_VERSION + j] != 0; j++ ){
    version[j] = (char)data[SW_PAYLOAD_FW_INFO_VERSION + j];
  }
  version[j] = '\0';

  if( this->handle_firmware_version == NULL ) return;

  this->handle_firmware_version(data[SW_PAYLOAD_FW_INFO_VALID], version);
}

void _SkyWriter::handle_sensor_data(unsigned char* data){
/*
  | HEADER | PAYLOAD
  |        |  DataOutputConfigMask 2 | TimeStamp 1 | SystemInfo 1 | Content |
  
  DataOutputConfigMask
  Bit 0 - DSPStatus
  Bit 1 - GestureInfo
  Bit 2 - TouchInfo
  Bit 3 - AirWheelInfo
  Bit 4 - XYZ Position
  Bit 5 - NoisePower
  Bit 6-7 - Reserved
  Bit 8-10 - ElectrodeConfiguration
  Bit 11 - CICData
  Bit 12 - SDData
  Bit 13-15 - Reserved
  
  SystemInfo
  Bit 0 - PositionValid, indicates xyz pos data is valid
  Bit 1 - AirWheelValid, indicates AirWheel is active and AirWheelInfo is vaid
  Bit 2 - RawDataValid, indicates CICData and SDData fields are valid
  Bit 3 - NoisePowerValid, indicates NoisePower field is valid
  Bit 4 - EnvironmentalNoise, indicates that environmental noise has been detected
  Bit 5 - Clipping, indicates that the ADCs are clipping
  Bit 6 - Reserved
  Bit 7 - DSPRunning, indicates the system is currently running
  DSPStatus - 2 bytes -
  GestureInfo - 4 bytes
  TouchInfo - 4 bytes
  AirWheelInfo - 2 bytes - first byte indicates rotation, ++ = clockwise, 32 = 1 rotation
  xyzPosition - 6 bytes - 1+2 = x, 3-4 = y, 5-6 = z
  NoisePower
  CICData
  SDData
*/  
      
      if( data[SW_PAYLOAD_HDR_CONFIGMASK] & SW_DATA_XYZ && data[SW_PAYLOAD_HDR_SYSINFO] & SW_SYS_POSITION ){
        // Valid XYZ position
        this->x = data[SW_PAYLOAD_X+1] << 8 | data[SW_PAYLOAD_X];
        this->y = data[SW_PAYLOAD_Y+1] << 8 | data[SW_PAYLOAD_Y];
        this->z = data[SW_PAYLOAD_Z+1] << 8 | data[SW_PAYLOAD_Z];
        
        if( handle_xyz != NULL ) handle_xyz(this->x,this->y,this->z);
      }
      
      if( data[SW_PAYLOAD_HDR_CONFIGMASK] & SW_DATA_GESTURE && data[SW_PAYLOAD_GESTURE] > 0){
        // Valid gesture
        //
        // GestureInfo is a 32-bit little-endian word (Interface.pdf §4.5,
        // Table 4-10): bits 0-7 = gesture code (1 garbage, 2-5 flicks, 6/7
        // circles), bits 12-15 = gesture class (1 flick, 2 circle), bit 16
        // = edge-flick flag, bit 31 = recognition in progress. Recognition
        // in progress ("hand moving, gesture not yet decided") frames carry
        // code 0, so the code>0 test above already emits nothing for them,
        // exactly as hid_mapping.md §2 requires — that part of the branch
        // is unchanged.
        // Deviation D7 (fix item P3.11): the old code read only byte 0 and
        // discarded class/edge; this decode now mirrors the Python driver's
        // reference implementation (library/skywriter/__init__.py, P3.7).
        uint32_t gesture_word =
              (uint32_t)data[SW_PAYLOAD_GESTURE]
            | (uint32_t)data[SW_PAYLOAD_GESTURE + 1] << 8
            | (uint32_t)data[SW_PAYLOAD_GESTURE + 2] << 16
            | (uint32_t)data[SW_PAYLOAD_GESTURE + 3] << 24;

        // The attributes become driver state (like x/y/z), mirroring the
        // Python driver's `gesture` / `gesture_class` / `gesture_edge`
        // globals, so a registered handler reads them alongside
        // `last_gesture`. They are set BEFORE the dispatch, so the handler
        // and the replay harness (tests/cpp/host_decoder_main.cpp prints
        // them from inside its onGesture callback) always see the values of
        // the gesture being dispatched.
        this->last_gesture       = gesture_word & 0xFF;          // bits 0-7: code
        this->last_gesture_class = (gesture_word >> 12) & 0xF;   // bits 12-15: class
        this->last_gesture_edge  = gesture_word & 0x10000;       // bit 16: edge flick

        if( this->handle_gesture != NULL ) this->handle_gesture(this->last_gesture);
      }
      
      if ( data[SW_PAYLOAD_HDR_CONFIGMASK] & SW_DATA_TOUCH ){
        // Valid touch. TouchInfo bits 0-14 are the touch / tap / doubletap
        // electrodes; this scan runs highest bit first (bit 14 = doubletap
        // center ... bit 0 = touch south), which is exactly the scan order
        // of the SW_* code constants in skywriter.h. EVERY set bit is
        // dispatched — a frame may carry several electrodes at once, and
        // hid_mapping.md §2 requires "all set touch bits in a frame produce
        // their events" (deviation D4: the old code returned after the
        // first match, which also skipped every field after TouchInfo,
        // including the AirWheel decode below).
        uint16_t touch_action = data[SW_PAYLOAD_TOUCH+1] << 8 | data[SW_PAYLOAD_TOUCH];
        uint16_t comp = 1 << 14;
        uint8_t x;
        for(x = 0; x < 16; x++){
          if( touch_action & comp ){
            this->last_touch = x;
            if( this->handle_touch != NULL ) this->handle_touch(this->last_touch);
          }
          comp = comp >> 1;
        }
      }
      
      if( data[SW_PAYLOAD_HDR_CONFIGMASK] & SW_DATA_AIRWHEEL && data[SW_PAYLOAD_HDR_SYSINFO] & SW_SYS_AIRWHEEL ){
        // AirWheel rotation, mirroring the Python driver's reference
        // implementation (library/skywriter/__init__.py, fix items P3.4 /
        // P3.9, deviation D3):
        //  * AirWheelInfo byte 0 is a free-running 8-bit rotation counter
        //    (0-255, wraps 255->0 clockwise, 32 counts = 1 revolution, so
        //    1 count = 11.25 degrees — Interface.pdf Table 4-10);
        //  * the counter is free-running, so the FIRST valid frame after
        //    driver start or after any stretch of AirWheel-invalid frames
        //    is a SILENT baseline: a hand re-entering the field must not be
        //    read against a stale counter (hid_mapping.md §2 baseline rule);
        //  * consecutive frames compare with the SIGNED 8-bit difference
        //    d = ((cur - last + 128) % 256) - 128, so a 255->0 wrap counts
        //    as +1 step, not -254.

        if( !this->airwheel_counter_valid ){
          // Silent baseline: record the reference only, emit nothing.
          this->airwheel_counter_valid = true;
          this->lastrotation = data[SW_PAYLOAD_AIRWHEEL];
        }
        else{
          int delta = (( data[SW_PAYLOAD_AIRWHEEL] - this->lastrotation + 128) % 256 + 256) % 256 - 128;
          
          // Delta is in degrees, quantized to 11.25 degrees per sensor step
          // (32 counts = full 360 degree rotation)
          // Positive numbers equal clockwise delta, negative are counter-clockwise
          float degrees = (float)delta * 11.25f;
          
          if( degrees != 0.0f ){
            if( this->handle_airwheel != NULL ) this->handle_airwheel(degrees);
            
            this->rotation += degrees;
            
            if( this->rotation < 0.0f ) this->rotation = 0.0f;
            if( this->rotation > 1000.0f ) this->rotation = 1000.0f;
          }
          
          this->lastrotation = data[SW_PAYLOAD_AIRWHEEL];
        }
      }
      else{
        // This frame carries no valid AirWheel data: the counter may have
        // free-run meanwhile, so re-baseline on the next valid frame
        // (same rule as the Python driver's `_lastrotation = None`).
        this->airwheel_counter_valid = false;
      }
}
