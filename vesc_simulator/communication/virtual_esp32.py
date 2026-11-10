"""ESP32 virtuel : interroge le répondeur comme un tableau de bord réel (démo sans matériel + tests)."""
from __future__ import annotations

import threading
import time

from communication import vesc_protocol as P
from communication.responder import VescResponder


class VirtualEsp32:
    def __init__(self, responder: VescResponder, hz: float = 10.0):
        self.responder, self.hz = responder, hz
        self.decoder = P.PacketDecoder()
        self.last_values: dict = {}
        self.last_setup: dict = {}
        self.running = False
        self.ok_count = self.timeouts = 0
        self._t: threading.Thread | None = None

    def poll_once(self) -> bool:
        got = False
        for cmd in (P.COMM_GET_VALUES, P.COMM_GET_VALUES_SETUP):
            for fr in self.decoder.feed(b"".join(self.responder.feed(P.request(cmd)))):
                if fr.ok:
                    d = P.parse_values_payload(fr.payload)
                    (self.last_values if cmd == P.COMM_GET_VALUES else self.last_setup).update(d)
                    got = True
        self.ok_count += got
        self.timeouts += (not got)
        return got

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.responder.feed(P.request(P.COMM_FW_VERSION))
        self._t = threading.Thread(target=self._loop, daemon=True, name="virtual-esp32")
        self._t.start()

    def stop(self) -> None:
        self.running = False
        if self._t:
            self._t.join(1.0)

    def _loop(self) -> None:
        while self.running:
            self.poll_once()
            time.sleep(1.0 / self.hz)
