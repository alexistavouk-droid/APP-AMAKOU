import struct

import pytest

from communication import vesc_protocol as P
from communication.frame_log import FrameLog
from communication.responder import VescResponder
from simulator.telemetry import Telemetry
from simulator.vesc_engine import VescEngine


def test_frame_short_and_long():
    assert P.frame_packet(b"\x04") == bytes([2, 1, 4, 0x40, 0x84, 3])
    big = bytes(range(256)) * 2
    f = P.frame_packet(big)
    assert f[:3] == bytes([3, 0x02, 0x00]) and f[-1] == 3
    out = P.PacketDecoder().feed(f)
    assert out[0].ok and out[0].payload == big


def test_decoder_bytewise_and_resync():
    dec = P.PacketDecoder()
    stream = b"\xff\x00" + P.request(4) + b"\x99" + P.request(0)
    got = []
    for b in stream:
        got += dec.feed(bytes([b]))
    assert [g.cmd_id for g in got if g.ok] == [4, 0]


def test_decoder_bad_crc_and_recovery():
    bad = bytearray(P.request(4))
    bad[3] ^= 0xFF
    out = P.PacketDecoder().feed(bytes(bad) + P.request(0))
    assert [f.ok for f in out] == [False, True] and out[0].error == "CRC invalide"
    assert out[0].crc_calc != out[0].crc_rx


def test_get_values_layout():
    v = Telemetry(temp_fet=41.3, temp_motor=55.5, i_motor=12.34, i_batt=-3.21, duty=0.456, erpm=12345,
                  v_in=52.4, fault=5, tachometer=-100).vesc_values()
    p = P.build_values_payload(P.COMM_GET_VALUES, v)
    assert len(p) == 74
    assert p[0] == 4
    assert struct.unpack(">h", p[1:3])[0] == 413
    assert struct.unpack(">i", p[5:9])[0] == 1234
    assert struct.unpack(">i", p[9:13])[0] == -321
    assert struct.unpack(">h", p[21:23])[0] == 456
    assert struct.unpack(">i", p[23:27])[0] == 12345
    assert struct.unpack(">h", p[27:29])[0] == 524
    assert p[53] == 5                       # champ "fault" (bit 15)
    d = P.parse_values_payload(p)
    assert d["rpm"] == 12345 and d["v_in"] == pytest.approx(52.4) and d["fault"] == 5


def test_get_values_setup_roundtrip():
    t = Telemetry(speed_kmh=36.0, soc_pct=87.5, v_in=50.2, distance_km=1.234, odometer_m=5000)
    p = P.build_values_payload(P.COMM_GET_VALUES_SETUP, t.vesc_setup_values())
    d = P.parse_values_payload(p)
    assert d["speed"] == pytest.approx(10.0)              # m/s dans le protocole
    assert d["battery_level"] == pytest.approx(0.875)
    assert d["distance"] == pytest.approx(1234.0)
    assert d["odometer"] == 5000


def test_selective_mask():
    t = Telemetry(erpm=777, v_in=48.0)
    mask = (1 << 7) | (1 << 8)                            # rpm + v_in
    p = P.build_values_payload(P.COMM_GET_VALUES_SELECTIVE, t.vesc_values(), mask)
    assert len(p) == 1 + 4 + 4 + 2
    d = P.parse_values_payload(p)
    assert d["rpm"] == 777 and d["v_in"] == pytest.approx(48.0) and "temp_fet" not in d


def test_fw_version():
    p = P.build_fw_version(P.FwInfo(7, 1, "HW_TEST"))
    d = P.parse_fw_version(p)
    assert (d["major"], d["minor"], d["hw_name"]) == (7, 1, "HW_TEST")


def make():
    eng = VescEngine()
    eng.running = True
    return eng, VescResponder(eng, FrameLog())


def decode_reply(frames):
    return P.PacketDecoder().feed(b"".join(frames))


def test_responder_get_values_and_fw():
    eng, r = make()
    out = decode_reply(r.feed(P.request(P.COMM_GET_VALUES)))
    assert out[0].ok and out[0].cmd_id == 4 and len(out[0].payload) == 74
    out = decode_reply(r.feed(P.request(P.COMM_FW_VERSION)))
    assert out[0].cmd_id == 0
    assert r.log.count("tx_frames") == 2 and r.log.count("rx_frames") == 2


@pytest.mark.parametrize("cmd", [5, 6, 7, 8, 9, 10, 13, 16, 29, 1, 2, 3])
def test_control_commands_blocked(cmd):
    eng, r = make()
    thr = eng.throttle
    assert r.feed(P.request(cmd, struct.pack(">i", 100000))) == []
    assert r.log.count("blocked_cmds") == 1 and eng.throttle == thr


def test_unknown_and_alive_and_crc_error():
    eng, r = make()
    assert r.feed(P.request(200)) == [] and r.log.count("unknown_cmds") == 1
    assert r.feed(P.request(P.COMM_ALIVE)) == []
    bad = bytearray(P.request(4)); bad[3] ^= 1
    assert r.feed(bytes(bad)) == [] and r.log.count("crc_errors") == 1


def test_link_down_and_corruption():
    eng, r = make()
    eng.link.link_up = False
    assert r.feed(P.request(4)) == []
    eng.link.link_up = True
    eng.link.crc_corrupt_rate = 1.0
    out = decode_reply(r.feed(P.request(4)))
    assert out and not out[0].ok


def test_forward_can():
    eng, r = make()
    assert decode_reply(r.feed(P.request(P.COMM_FORWARD_CAN, bytes([0, P.COMM_GET_VALUES]))))[0].cmd_id == 4
    assert r.feed(P.request(P.COMM_FORWARD_CAN, bytes([9, P.COMM_GET_VALUES]))) == []
