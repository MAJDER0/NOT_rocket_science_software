/// we want the same frame field as in communication_library/frame.py
///
/// each field has a fixed bit width in the protocol:
/// destination:    5 bits
/// priority:       2 bits
/// action:         4 bits
/// source:         5 bits
/// device_type:    6 bits
/// device_id:      6 bits
/// data_type:      4 bits
/// operation:      8 bits
///
/// payload:        32 bits (4 bytes) - e.g. float32 / int16 / etc
///
/// the final packet without CRC looks like this:
///   [HEADER_ID (1 byte)]
///   [above fields tightly bit-packed into 5 bytes]
///   [payload (4 bytes)] 
/// 
/// so its 10 bytes in total (I did math in my head)
///
/// every byte has its bit order reversed (LSB <-> MSB)
/// and only then the CRC32 MPEG-2 (4 bytes) is appended
/// producing the final 14 bytes sent over TCP
///
/// ^ this is what GroundStationProtocol.encode() does and we want the same

pub const HEADER_ID: u8 = 0x05;

#[derive(Debug, Clone)]
pub struct FrameFields {
    pub destination: u8,   // 5 bits
    pub priority: u8,      // 2 bits
    pub action: u8,        // 4 bits
    pub source: u8,        // 5 bits
    pub device_type: u8,   // 6 bits
    pub device_id: u8,     // 6 bits
    pub data_type: u8,     // 4 bits
    pub operation: u8,     // 8 bits

    /// exactly 4 bytes of payload converted
    pub payload: [u8; 4],
}

/// pack_frame_bits:
///  - builds the raw 10-byte frame (HEADER + fields + payload)
///  - without bit-reversal and without CRC for now
///
/// in the final version this must do the same bit packing
/// as python does with bitstruct '<u5u2u4u5u6u6u4u8'

pub fn pack_frame_bits(frame: &FrameFields) -> [u8; 10] {
    let mut out = [0u8; 10];

    // Byte 0: HEADER_ID
    out[0] = HEADER_ID;

    // Bytes from 1 to 5: bit-packed fields
    //
    // TODO: pack:
    //   destination (5)
    //   priority    (2)
    //   action      (4)
    //   source      (5)
    //   device_type (6)
    //   device_id   (6)
    //   data_type   (4)
    //   operation   (8)
    //
    // currently just placeholders so it compiles.
    // In the real version everything goes tightly into 5 bytes exactly like python's bitstruct packing
    out[1] = frame.destination & 0x1F; // lower 5 bits
    out[2] = frame.priority & 0x03;
    out[3] = frame.action & 0x0F;
    out[4] = frame.source & 0x1F;
    // etc
    // final code will combine fields across byte boundaries

    // bytes from 6 to 9: payload (4 bytes)
    out[6] = frame.payload[0];
    out[7] = frame.payload[1];
    out[8] = frame.payload[2];
    out[9] = frame.payload[3];

    out
}

/// reverse the bit order within a single byte
/// looks nice in python but will look worse here xD : int(f'{byte:08b}'[::-1], 2) - python ahh moment 
pub fn reverse_bits_in_byte(b: u8) -> u8 {
    let mut x = b;
    x = (x >> 4) | (x << 4);
    x = ((x & 0b11001100) >> 2) | ((x & 0b00110011) << 2);
    x = ((x & 0b10101010) >> 1) | ((x & 0b01010101) << 1);
    x
}

/// return new bytes after reversing the bit order of every byte in the input
pub fn reverse_all_bytes(bytes_in: &[u8]) -> Vec<u8> {
    bytes_in.iter().map(|b| reverse_bits_in_byte(*b)).collect()
}
