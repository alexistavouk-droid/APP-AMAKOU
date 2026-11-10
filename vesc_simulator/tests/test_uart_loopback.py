"""Boucle locale : un « ESP32 virtuel » (client VescUart-like) parle au UartServer via un vrai port série
(pseudo-terminal POSIX ; sous Windows utiliser com0com, voir README)."""
import os
import sys
import threading
import time

import pytest

from communication import vesc_protocol as P
from communication.frame_log import FrameLog
from communication.responder import VescResponder
from communication.uart_server import UartServer
from simulator.vesc_engine import VescEngine
from tests.vescuart_client import VescUartLike, pack

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="pty POSIX requis")


@pytest.fixture
def rig():
    eng = VescEngine(); eng.running = True
    eng.set_override("rpm", 300); eng.set_override("v_in", 51.2); eng.set_override("temp_motor", 61.5)
    eng.step(0.02)
    log = FrameLog()
    srv = UartServer(VescResponder(eng, log))
    master, slave = os.openpty()
    srv.start(os.ttyname(slave), 115200)
    yield eng, log, srv, master
    srv.stop()
    os.close(master); os.close(slave)


def test_client_receives_valid_values(rig):
    eng, log, srv, fd = rig
    cl = VescUartLike(fd)
    assert cl.get_fw() == (7, 1)
    v = cl.get_values()
    assert v is not None
    assert v["rpm"] == 300 * eng.cfg.pole_pairs
    assert v["inpVoltage"] == pytest.approx(51.2)
    assert v["tempMotor"] == pytest.approx(61.5)
    assert v["error"] == 0
    assert log.count("crc_errors") == 0


def test_stability_many_requests(rig):
    eng, log, srv, fd = rig
    cl = VescUartLike(fd)
    for i in range(300):
        assert cl.get_values() is not None, f"requête {i} sans réponse"
    assert log.count("rx_frames") == 300 and log.count("tx_frames") == 300


def test_split_and_noisy_input(rig):
    eng, log, srv, fd = rig
    frame = pack(b"\x04")
    os.write(fd, b"\x00\xff")                   # bruit
    for b in frame:                             # octet par octet
        os.write(fd, bytes([b])); time.sleep(0.002)
    assert VescUartLike(fd)._read_frame() is not None


def test_link_loss_and_return(rig):
    eng, log, srv, fd = rig
    cl = VescUartLike(fd)
    assert cl.get_values() is not None
    eng.link.link_up = False
    os.write(fd, pack(b"\x04"))
    assert cl._read_frame(0.3) is None          # l'ESP32 doit détecter l'absence de réponse
    eng.link.link_up = True
    assert cl.get_values() is not None          # retour de connexion


def test_reconnect_port():
    eng = VescEngine(); eng.running = True
    srv = UartServer(VescResponder(eng, FrameLog()))
    for _ in range(3):
        master, slave = os.openpty()
        srv.start(os.ttyname(slave), 115200)
        assert VescUartLike(master).get_values() is not None
        srv.stop()
        os.close(master); os.close(slave)
    assert not srv.connected


def test_push_mode(rig):
    eng, log, srv, fd = rig
    srv.set_push(20, P.COMM_GET_VALUES)
    cl = VescUartLike(fd)
    p = cl._read_frame(1.0)
    srv.set_push(0)
    assert p is not None and p[0] == 4


def test_blocked_command_over_uart(rig):
    eng, log, srv, fd = rig
    os.write(fd, pack(bytes([P.COMM_SET_CURRENT, 0, 0, 0x27, 0x10])))
    assert VescUartLike(fd)._read_frame(0.3) is None
    time.sleep(0.05)
    assert log.count("blocked_cmds") == 1 and eng.throttle == 0
