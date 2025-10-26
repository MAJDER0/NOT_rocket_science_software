use rust_protocol::{FrameFields, encode_frame};

#[test]
fn encode_sample_frame_and_print() {
    // simulate a SERVICE command to the fuel_main servo (set position to 0)
    //
    // fields does the same what python sends in CommunicationManager:
    // destination = ROCKET (0x02)
    // priority    = LOW (0x01)
    // action      = SERVICE (0x01)
    // source      = SOFTWARE (0x01)
    // device_type = SERVO (0x00)
    // device_id   = 0x02 (e.g. fuel_main)
    // data_type   = INT16 (0x05)
    // operation   = POSITION (0x05)
    // payload     = [0,0,0,0]  (i.e. set position to 0)

    let frame = FrameFields {
        destination: 0x02,
        priority:    0x01,
        action:      0x01,
        source:      0x01,
        device_type: 0x00,
        device_id:   0x02,
        data_type:   0x05,
        operation:   0x05,
        payload:     [0x00, 0x00, 0x00, 0x00],
    };

    let encoded = encode_frame(&frame);

    println!("Encoded frame bytes (hex): {:02X?}", encoded);
    println!("Length: {}", encoded.len());

    // 10 bytes of data after reverse_bits
    // 4 bytes of CRC32 MPEG-2
    // 14 in total
    assert_eq!(encoded.len(), 14, "frame should be 14 bytes total");
}
