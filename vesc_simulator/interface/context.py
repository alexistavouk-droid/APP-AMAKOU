"""Contexte applicatif : objets partagés entre les onglets."""
from __future__ import annotations

from communication.frame_log import FrameLog
from communication.responder import VescResponder
from communication.uart_server import UartServer
from communication.virtual_esp32 import VirtualEsp32
from simulator.dashboard_test import DashboardTester
from simulator.profiles import load_profile
from simulator.vesc_engine import VescEngine


class AppContext:
    def __init__(self):
        try:
            cfg = load_profile("default")
        except Exception:
            from simulator.vesc_engine import SimConfig
            cfg = SimConfig()
        self.engine = VescEngine(cfg)
        self.log = FrameLog(to_file=True)
        self.responder = VescResponder(self.engine, self.log, "UART")
        self.uart = UartServer(self.responder)
        self.virtual = VirtualEsp32(self.responder)
        self.tester = DashboardTester(self.engine, self.log)
        self.ble = None
        self.can = None
        self.transport = "—"
        self.ble_address = ""

    def shutdown(self) -> None:
        for fn in (self.virtual.stop, self.uart.stop, self.engine.shutdown):
            try:
                fn()
            except Exception:
                pass
        for o in (self.ble, self.can):
            try:
                o and o.stop()
            except Exception:
                pass
