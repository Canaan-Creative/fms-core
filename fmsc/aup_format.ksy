meta:
  id: aup_header
  file-extension: aup
  endian: le
seq:
  - id: magic
    size: 16
    type: str
    encoding: UTF-8
  - id: fmt_ver
    type: u4
  - id: header_data
    type:
      switch-on: fmt_ver
      cases:
        '0': aup0
        '1': aup1
        '2': aup2
types:
  aup0:
    seq:
      - id: payload_len
        type: u4
      - id: firmware_ver
        type: str
        encoding: UTF-8
        size: 64
      - id: payload_crc
        type: u4
  aup1:
    seq:
      - id: header_len
        type: u4
      - id: hw_list
        type: comma_separated_str_list
        size: 128
      - id: payload_len
        type: u4
      - id: firmware_ver
        type: str
        encoding: UTF-8
        size: 64
      - id: payload_crc
        type: u4
  aup2:
    seq:
      - id: payload_len
        type: u4
      - id: firmware_ver
        type: str
        encoding: UTF-8
        size: 64
      - id: payload_crc
        type: u4
      - id: hw_list_count
        type: u4
      - id: sw_list_count
        type: u4
      - id: hw_list
        type: fixed_32_str
        repeat: expr
        repeat-expr: hw_list_count
      - id: sw_list
        type: fixed_32_str
        repeat: expr
        repeat-expr: sw_list_count
  comma_separated_str_list:
    seq:
      - id: hw_str_list
        type: str
        encoding: UTF-8
        terminator: 0x2c
        eos-error: false
        repeat: eos
  fixed_32_str:
    seq:
      - id: str_value
        type: str
        encoding: UTF-8
        size: 32
        terminator: 0

