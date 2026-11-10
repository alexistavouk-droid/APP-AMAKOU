"""Client indépendant écrit comme la bibliothèque Arduino VescUart (SolidGeek) : requête GET_VALUES,
extraction du payload par l'en-tête 0x02/0x03, vérification CRC, décodage à offsets fixes.
Sert d'« ESP32 virtuel » : il n'utilise PAS le code du simulateur (CRC recalculé bit à bit)."""
import os
import select
import struct
import time


def crc16_bitwise(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def pack(payload: bytes) -> bytes:
    crc = crc16_bitwise(payload)
    return bytes([2, len(payload)]) + payload + struct.pack(">H", crc) + b"\x03"


class VescUartLike:
    def __init__(self, fd: int):
        self.fd = fd

    def _read_frame(self, timeout=1.0):
        buf = b""
        end = time.time() + timeout
        while time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if r:
                buf += os.read(self.fd, 4096)
            if len(buf) >= 2 and buf[0] in (2, 3):
                hl = 1 if buf[0] == 2 else 2
                n = int.from_bytes(buf[1:1 + hl], "big")
                if len(buf) >= 1 + hl + n + 3:
                    payload = buf[1 + hl:1 + hl + n]
                    crc_rx = struct.unpack(">H", buf[1 + hl + n:3 + hl + n])[0]
                    assert buf[-1] == 3, "octet de fin"
                    assert crc_rx == crc16_bitwise(payload), "CRC réponse invalide"
                    return payload
        return None

    def get_values(self):
        os.write(self.fd, pack(b"\x04"))
        p = self._read_frame()
        if p is None:
            return None
        assert p[0] == 4
        o = 1
        r = {}
        for name, fmt, sc in [("tempMosfet", ">h", 10), ("tempMotor", ">h", 10), ("avgMotorCurrent", ">i", 100),
                              ("avgInputCurrent", ">i", 100), ("avgId", ">i", 100), ("avgIq", ">i", 100),
                              ("dutyCycleNow", ">h", 1000), ("rpm", ">i", 1), ("inpVoltage", ">h", 10),
                              ("ampHours", ">i", 10000), ("ampHoursCharged", ">i", 10000),
                              ("wattHours", ">i", 10000), ("wattHoursCharged", ">i", 10000),
                              ("tachometer", ">i", 1), ("tachometerAbs", ">i", 1)]:
            v = struct.unpack_from(fmt, p, o)[0]
            o += struct.calcsize(fmt)
            r[name] = v / sc
        r["error"] = p[o]
        return r

    def get_fw(self):
        os.write(self.fd, pack(b"\x00"))
        p = self._read_frame()
        return None if p is None else (p[1], p[2])
