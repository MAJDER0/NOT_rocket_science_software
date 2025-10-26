/// CRC32 MPEG-2
/// Parameters:
/// - Poly:    0x04C11DB7
/// - Init:    0xFFFFFFFF
/// - RefIn:   false
/// - RefOut:  false
/// - XorOut:  0x00000000
///
///  how python implementation works:
///   - takes the bytes after bit-reversing each byte (reverse_all_bytes)
///   - pads to a multiple of 4 bytes with zeros
///   - interprets them as 32-bit words and packs each word to big-endian
///   - computes CRC32 MPEG-2
///   - returns the CRC as 4 bytes in little endian
///
/// we want write the same in language for goats (first time coding in rust)

pub fn crc32_mpeg2_with_padding(data_in: &[u8]) -> [u8; 4] {
    // pad to a multiple of 4 bytes
    let mut padded = data_in.to_vec();
    let rem = padded.len() % 4;
    if rem != 0 {
        let pad = 4 - rem;
        padded.extend(std::iter::repeat(0u8).take(pad));
    }

    // for each 4-byte chunk:
    //    - read it as u32 in native endian
    //    - write it out as big-endian bytes
    let mut be_words: Vec<u8> = Vec::with_capacity(padded.len());
    for chunk in padded.chunks_exact(4) {
        let w = u32::from_ne_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]);
        let be = w.to_be_bytes();
        be_words.extend_from_slice(&be);
    }

    // compute crc32 MPEG-2 without bit reflection
    let poly: u32 = 0x04C11DB7;
    let mut crc: u32 = 0xFFFFFFFF;

    for &byte in &be_words {
        let mut cur = (byte as u32) << 24;
        for _ in 0..8 {
            let bit = (crc ^ cur) & 0x80000000;
            crc = (crc << 1) ^ if bit != 0 { poly } else { 0 };
            cur <<= 1;
        }
    }

    // XorOut = 0x00000000, so crc stays as-is

    // return CRC as 4 bytes in little endian
    crc.to_le_bytes()
}

