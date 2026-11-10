import binascii
import random

from communication.vesc_protocol import CRC16_TAB, crc16, request


def test_crc_xmodem_check_value():
    assert crc16(b"123456789") == 0x31C3          # CRC-16/XMODEM (poly 0x1021, init 0)


def test_table_matches_firmware_crc_c():
    # premières / dernières entrées de crc16_tab[] dans util/crc.c du firmware VESC
    assert CRC16_TAB[:6] == [0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50A5]
    assert CRC16_TAB[-2:] == [0x0ED1, 0x1EF0]


def test_against_stdlib_crc_hqx():
    rnd = random.Random(1)
    for _ in range(200):
        data = bytes(rnd.randrange(256) for _ in range(rnd.randrange(1, 300)))
        assert crc16(data) == binascii.crc_hqx(data, 0)


def test_reference_frames_vesc_tool():
    # trames de requête émises par VESC Tool / VescUart
    assert request(4).hex() == "020104408403"      # COMM_GET_VALUES
    assert request(0).hex() == "020100000003"      # COMM_FW_VERSION
