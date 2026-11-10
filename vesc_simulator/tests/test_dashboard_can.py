import struct
import time

from communication import vesc_protocol as P
from communication.can_interface import (CAN_PACKET_PING, CAN_PACKET_PONG, CAN_PACKET_STATUS,
                                         CanInterface, build_status_frames, can_id)
from communication.frame_log import FrameLog
from communication.responder import VescResponder
from simulator.dashboard_test import DashboardTester
from simulator.vesc_engine import VescEngine


def test_dashboard_checks_flow():
    eng = VescEngine(); eng.running = True
    log = FrameLog()
    r = VescResponder(eng, log)
    clock = [1000.0]
    t = DashboardTester(eng, log, clock=lambda: clock[0])
    assert {c.name: c.status for c in t.checks()}["Connexion"] == "ATTENTE"
    r.feed(P.request(P.COMM_GET_VALUES))
    r.feed(P.request(P.COMM_GET_VALUES_SETUP))
    st = {c.name: c.status for c in t.checks()}
    assert st["Connexion"] == "OK" and st["Réception des RPM"] == "OK" and st["État de la batterie"] == "OK"
    t.start_link_test(2.0)
    assert not eng.link.link_up
    assert r.feed(P.request(P.COMM_GET_VALUES)) == []
    clock[0] += 2.5; t.tick()
    assert eng.link.link_up and t.link_phase == "restored"
    r.feed(P.request(P.COMM_GET_VALUES)); clock[0] += 0.1; t.tick()
    assert t.link_phase == "done" and t.outage_requests == 1


def test_reference_vector():
    eng = VescEngine(); eng.running = True
    t = DashboardTester(eng, FrameLog())
    t.apply_reference_vector(); eng.step(0.02)
    s = eng.snapshot()
    assert s.v_in == 48.0 and s.i_batt == 10.0 and s.temp_motor == 55.0 and abs(s.rpm_mech - 500) < 1e-6
    assert any("RPM" in row[0] for row in t.sent_table())


def test_can_status_frames_layout():
    eng = VescEngine(); eng.running = True
    eng.set_override("rpm", 100); eng.set_override("v_in", 50.0); eng.step(0.02)
    frames = dict(build_status_frames(eng.snapshot(), 7))
    erpm, cur, duty = struct.unpack(">ihh", frames[can_id(CAN_PACKET_STATUS, 7)])
    assert erpm == 100 * eng.cfg.pole_pairs and can_id(CAN_PACKET_STATUS, 7) == 0x907
    assert struct.unpack(">ihh", frames[can_id(27, 7)])[1] == 500


def test_can_virtual_bus_ping():
    import can
    eng = VescEngine(); eng.running = True
    ci = CanInterface(eng); ci.start("virtual", "t_vesc", node_id=5)
    peer = can.Bus(interface="virtual", channel="t_vesc")
    try:
        peer.send(can.Message(arbitration_id=can_id(CAN_PACKET_PING, 5), data=bytes([99]), is_extended_id=True))
        got_status = got_pong = False
        end = time.time() + 2
        while time.time() < end and not (got_status and got_pong):
            m = peer.recv(0.1)
            if m is None:
                continue
            got_status |= m.arbitration_id == can_id(CAN_PACKET_STATUS, 5)
            got_pong |= m.arbitration_id == can_id(CAN_PACKET_PONG, 99) and m.data[0] == 5
        assert got_status and got_pong
    finally:
        ci.stop(); peer.shutdown()
