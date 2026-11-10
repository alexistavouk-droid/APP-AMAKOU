"""Serveur UART/USB : l'ESP32 interroge, le simulateur répond avec des trames VESC valides."""
from __future__ import annotations

import threading
import time

from communication import vesc_protocol as P
from communication.frame_log import LogEntry
from communication.responder import VescResponder

DEFAULT_BAUD = 115200   # débit UART par défaut du VESC


def list_ports() -> list[tuple[str, str]]:
    try:
        from serial.tools import list_ports as lp
        return [(p.device, p.description) for p in lp.comports()]
    except Exception:
        return []


class UartServer:
    def __init__(self, responder: VescResponder, serial_factory=None):
        self.responder = responder
        self.log = responder.log
        self._factory = serial_factory
        self.ser = None
        self.port = ""
        self.baud = DEFAULT_BAUD
        self.connected = False
        self.push_hz = 0.0            # >0 : envoi périodique non sollicité (désactivé par défaut)
        self.push_cmd = P.COMM_GET_VALUES
        self.bytes_rx = self.bytes_tx = 0
        self.last_error = ""
        self._stop = threading.Event()
        self._wlock = threading.Lock()
        self._threads: list[threading.Thread] = []

    def start(self, port: str, baud: int = DEFAULT_BAUD) -> None:
        if self.connected:
            self.stop()
        import serial
        factory = self._factory or (lambda p, b: serial.serial_for_url(
            p, baudrate=b, timeout=0.02, write_timeout=1.0))
        self.ser = factory(port, baud)
        self.port, self.baud = port, baud
        self.connected = True
        self.last_error = ""
        self._stop.clear()
        self.responder.decoder.reset()
        self.log.info(f"Port {port} ouvert à {baud} bauds", "INFO", "UART")
        t = threading.Thread(target=self._rx_loop, name="uart-rx", daemon=True)
        t.start()
        self._threads = [t]
        if self.push_hz > 0:
            self.set_push(self.push_hz, self.push_cmd)

    def set_push(self, hz: float, cmd: int = P.COMM_GET_VALUES) -> None:
        self.push_hz, self.push_cmd = hz, cmd
        if hz > 0 and self.connected and not any(t.name == "uart-push" and t.is_alive()
                                                 for t in self._threads):
            t = threading.Thread(target=self._push_loop, name="uart-push", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(0.5)
        self._threads = []
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        if self.connected:
            self.log.info(f"Port {self.port} fermé", "INFO", "UART")
        self.connected = False
        self.ser = None

    # --------------------------------------------------------------- threads
    def _write(self, data: bytes) -> None:
        with self._wlock:
            self.ser.write(data)
            self.bytes_tx += len(data)

    def _rx_loop(self) -> None:
        try:
            while not self._stop.is_set():
                n = getattr(self.ser, "in_waiting", 0) or 1
                data = self.ser.read(n)
                if not data:
                    continue
                self.bytes_rx += len(data)
                for frame in self.responder.feed(data):
                    self._write(frame)
        except Exception as exc:  # port retiré, erreur driver…
            self.last_error = str(exc)
            self.log.add(LogEntry(time.time(), "ERR", "UART", message=f"Erreur liaison série : {exc}"))
            self.connected = False

    def _push_loop(self) -> None:
        while not self._stop.is_set() and self.push_hz > 0:
            time.sleep(1.0 / self.push_hz)
            eng = self.responder.engine
            if not eng.link.link_up or not self.connected:
                continue
            try:
                payload = self.responder.process_payload(bytes([self.push_cmd]))
                if payload:
                    frame = P.frame_packet(payload)
                    self._write(frame)
                    self.log.add(LogEntry(time.time(), "TX", "UART", payload[0], P.comm_name(payload[0]),
                                          len(payload), P.crc16(payload), P.crc16(payload), True,
                                          frame.hex(" "), "envoi périodique"))
            except Exception as exc:
                self.log.add(LogEntry(time.time(), "ERR", "UART", message=str(exc)))
