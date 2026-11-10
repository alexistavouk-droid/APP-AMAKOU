"""Extension CAN (optionnelle, python-can) : diffusion des messages STATUS 1-5 du VESC.

ID étendu 29 bits = (commande << 8) | id du nœud  (comm_can.c). Formats vérifiés dans comm_can.c :
  STATUS(9)   : ERPM i32 | courant*10 i16 | duty*1000 i16
  STATUS_2(14): Ah*1e4 i32 | Ah chargés*1e4 i32
  STATUS_3(15): Wh*1e4 i32 | Wh chargés*1e4 i32
  STATUS_4(16): temp_fet*10 i16 | temp_moteur*10 i16 | courant_in*10 i16 | pid_pos*50 i16
  STATUS_5(27): tachymètre i32 | v_in*10 i16
  PING(17) -> PONG(18) : data=[id demandeur] -> réponse [id nœud, HW_TYPE_VESC=0]
Les échanges COMM_* (GET_VALUES…) via CAN (PROCESS_SHORT_BUFFER) ne sont PAS émulés.
"""
from __future__ import annotations

import struct
import threading
import time

CAN_PACKET_STATUS, CAN_PACKET_STATUS_2, CAN_PACKET_STATUS_3 = 9, 14, 15
CAN_PACKET_STATUS_4, CAN_PACKET_STATUS_5 = 16, 27
CAN_PACKET_PING, CAN_PACKET_PONG = 17, 18


def _i16(v, s):
    return max(-32768, min(32767, int(v * s)))


def _i32(v, s):
    return max(-2**31, min(2**31 - 1, int(v * s)))


def can_id(cmd: int, node: int) -> int:
    return (cmd << 8) | (node & 0xFF)


def build_status_frames(tel, node_id: int) -> list[tuple[int, bytes]]:
    return [
        (can_id(CAN_PACKET_STATUS, node_id),
         struct.pack(">ihh", _i32(tel.erpm, 1), _i16(tel.i_motor, 10), _i16(tel.duty, 1000))),
        (can_id(CAN_PACKET_STATUS_2, node_id),
         struct.pack(">ii", _i32(tel.ah_used, 1e4), _i32(tel.ah_regen, 1e4))),
        (can_id(CAN_PACKET_STATUS_3, node_id),
         struct.pack(">ii", _i32(tel.wh_used, 1e4), _i32(tel.wh_regen, 1e4))),
        (can_id(CAN_PACKET_STATUS_4, node_id),
         struct.pack(">hhhh", _i16(tel.temp_fet, 10), _i16(tel.temp_motor, 10),
                     _i16(tel.i_batt, 10), 0)),
        (can_id(CAN_PACKET_STATUS_5, node_id),
         struct.pack(">ihh", tel.tachometer, _i16(tel.v_in, 10), 0)),
    ]


class CanInterface:
    def __init__(self, engine, log=None):
        self.engine, self.log = engine, log
        self.bus = None
        self.node_id = engine.cfg.controller_id
        self.rate_hz = 50.0
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self, interface: str = "virtual", channel: str = "vesc_sim", bitrate: int = 500000,
              node_id: int | None = None) -> None:
        import can  # python-can (dépendance optionnelle)
        if node_id is not None:
            self.node_id = node_id
        self.bus = can.Bus(interface=interface, channel=channel, bitrate=bitrate)
        self._stop.clear()
        self._threads = [threading.Thread(target=self._tx, daemon=True),
                         threading.Thread(target=self._rx, daemon=True)]
        for t in self._threads:
            t.start()
        if self.log:
            self.log.info(f"CAN démarré ({interface}/{channel}, nœud {self.node_id})", "INFO", "CAN")

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(0.5)
        if self.bus:
            self.bus.shutdown()
            self.bus = None

    def _tx(self) -> None:
        import can
        while not self._stop.is_set():
            time.sleep(1.0 / self.rate_hz)
            if not self.engine.link.link_up:
                continue
            for arb, data in build_status_frames(self.engine.snapshot(), self.node_id):
                try:
                    self.bus.send(can.Message(arbitration_id=arb, data=data, is_extended_id=True))
                except Exception:
                    break

    def _rx(self) -> None:
        import can
        while not self._stop.is_set():
            try:
                msg = self.bus.recv(0.05)
            except Exception:
                break
            if msg is None or not msg.is_extended_id:
                continue
            cmd, node = msg.arbitration_id >> 8, msg.arbitration_id & 0xFF
            if cmd == CAN_PACKET_PING and node == self.node_id and msg.dlc >= 1:
                reply = can.Message(arbitration_id=can_id(CAN_PACKET_PONG, msg.data[0]),
                                    data=bytes([self.node_id, 0]), is_extended_id=True)
                self.bus.send(reply)
