mod frame;
mod crc;

pub use frame::{FrameFields, pack_frame_bits, reverse_all_bytes, HEADER_ID};
pub use crc::crc32_mpeg2_with_padding;

/// encode_frame:
///   same function as GroundStationProtocol.encode(frame) in python
///
/// what it does?
/// 1. pack_frame_bits  -> 10 bytes (HEADER + fields + payload)
/// 2. reverse_all_bytes -> reverse bits in every byte
/// 3. crc32_mpeg2_with_padding -> compute CRC on those bit-reversed bytes
/// 4. concat [reversed_bytes || crc] => final 14 bytes

pub fn encode_frame(frame: &FrameFields) -> Vec<u8> {
    let raw10 = pack_frame_bits(frame);

    let reversed = reverse_all_bytes(&raw10);

    let crc_le = crc32_mpeg2_with_padding(&reversed);

    let mut out = Vec::with_capacity(reversed.len() + crc_le.len());
    out.extend_from_slice(&reversed);
    out.extend_from_slice(&crc_le);
    out
}


