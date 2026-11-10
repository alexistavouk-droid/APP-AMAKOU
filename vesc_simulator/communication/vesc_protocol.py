"""Protocole VESC (framing, CRC16, charges utiles).

Référence : firmware officiel https://github.com/vedderb/bldc (v7.01)
  - util/crc.c      : CRC16 (poly 0x1021, init 0, = CRC-16/XMODEM)
  - comm/packet.c   : framing  [0x02 len | 0x03 len16 | 0x04 len24] payload crc16(BE) 0x03
  - comm/commands.c : COMM_FW_VERSION, COMM_GET_VALUES(_SELECTIVE), COMM_GET_VALUES_SETUP(_SELECTIVE)
  - util/buffer.c   : entiers big-endian, "float" = int(valeur * échelle)
  - datatypes.h     : identifiants COMM_*, codes de défaut
Aucune structure n'est inventée : les tables ci-dessous reprennent l'ordre des bits du firmware.
"""
from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- IDs
COMM_FW_VERSION = 0
COMM_GET_VALUES = 4
COMM_SET_DUTY = 5
COMM_SET_CURRENT = 6
COMM_SET_CURRENT_BRAKE = 7
COMM_SET_RPM = 8
COMM_SET_POS = 9
COMM_SET_HANDBRAKE = 10
COMM_SET_DETECT = 11
COMM_SET_SERVO_POS = 12
COMM_SET_MCCONF = 13
COMM_GET_MCCONF = 14
COMM_GET_MCCONF_DEFAULT = 15
COMM_SET_APPCONF = 16
COMM_GET_APPCONF = 17
COMM_GET_APPCONF_DEFAULT = 18
COMM_TERMINAL_CMD = 20
COMM_REBOOT = 29
COMM_ALIVE = 30
COMM_FORWARD_CAN = 34
COMM_SET_CHUCK_DATA = 35
COMM_CUSTOM_APP_DATA = 36
COMM_GET_VALUES_SETUP = 47
COMM_SET_MCCONF_TEMP = 48
COMM_SET_MCCONF_TEMP_SETUP = 49
COMM_GET_VALUES_SELECTIVE = 50
COMM_GET_VALUES_SETUP_SELECTIVE = 51
COMM_PING_CAN = 62
COMM_APP_DISABLE_OUTPUT = 63
COMM_GET_IMU_DATA = 65

COMM_NAMES = {
    0: "COMM_FW_VERSION", 1: "COMM_JUMP_TO_BOOTLOADER", 2: "COMM_ERASE_NEW_APP",
    3: "COMM_WRITE_NEW_APP_DATA", 4: "COMM_GET_VALUES", 5: "COMM_SET_DUTY",
    6: "COMM_SET_CURRENT", 7: "COMM_SET_CURRENT_BRAKE", 8: "COMM_SET_RPM",
    9: "COMM_SET_POS", 10: "COMM_SET_HANDBRAKE", 11: "COMM_SET_DETECT",
    12: "COMM_SET_SERVO_POS", 13: "COMM_SET_MCCONF", 14: "COMM_GET_MCCONF",
    15: "COMM_GET_MCCONF_DEFAULT", 16: "COMM_SET_APPCONF", 17: "COMM_GET_APPCONF",
    18: "COMM_GET_APPCONF_DEFAULT", 20: "COMM_TERMINAL_CMD", 21: "COMM_PRINT",
    29: "COMM_REBOOT", 30: "COMM_ALIVE", 31: "COMM_GET_DECODED_PPM",
    32: "COMM_GET_DECODED_ADC", 33: "COMM_GET_DECODED_CHUK", 34: "COMM_FORWARD_CAN",
    35: "COMM_SET_CHUCK_DATA", 36: "COMM_CUSTOM_APP_DATA", 47: "COMM_GET_VALUES_SETUP",
    48: "COMM_SET_MCCONF_TEMP", 49: "COMM_SET_MCCONF_TEMP_SETUP",
    50: "COMM_GET_VALUES_SELECTIVE", 51: "COMM_GET_VALUES_SETUP_SELECTIVE",
    62: "COMM_PING_CAN", 63: "COMM_APP_DISABLE_OUTPUT", 65: "COMM_GET_IMU_DATA",
}

# Commandes de lecture que le simulateur traite.
READ_COMMANDS = {
    COMM_FW_VERSION, COMM_GET_VALUES, COMM_GET_VALUES_SELECTIVE,
    COMM_GET_VALUES_SETUP, COMM_GET_VALUES_SETUP_SELECTIVE, COMM_PING_CAN,
}
# Keep-alive : accepté, sans réponse (comme le firmware), aucun effet.
PASSIVE_COMMANDS = {COMM_ALIVE}
# Commandes de pilotage / configuration / mise à jour : TOUJOURS bloquées (sécurité).
BLOCKED_COMMANDS = {
    1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16, 18, 19, 20, 24, 25, 26, 27, 28, 29,
    35, 36, 38, 39, 40, 41, 42, 43, 44, 45, 46, 48, 49, 57, 58, 59, 60, 61, 63, 64,
}
# Commandes de lecture connues mais non émulées (structures trop volumineuses : jamais inventées).
UNSUPPORTED_READ_COMMANDS = {COMM_GET_MCCONF, COMM_GET_APPCONF, COMM_GET_IMU_DATA, 31, 32, 33}

# Codes de défaut (datatypes.h : mc_fault_code)
FAULT_NONE = 0
FAULT_OVER_VOLTAGE = 1
FAULT_UNDER_VOLTAGE = 2
FAULT_DRV = 3
FAULT_ABS_OVER_CURRENT = 4
FAULT_OVER_TEMP_FET = 5
FAULT_OVER_TEMP_MOTOR = 6
FAULT_UNBALANCED_CURRENTS = 17
FAULT_ENCODER_FAULT = 28
FAULT_NAMES = {
    0: "AUCUN", 1: "SURTENSION", 2: "SOUS-TENSION", 3: "DRV", 4: "SURINTENSITÉ ABS",
    5: "SURCHAUFFE MOSFET", 6: "SURCHAUFFE MOTEUR", 7: "GATE DRIVER SURTENSION",
    8: "GATE DRIVER SOUS-TENSION", 9: "MCU SOUS-TENSION", 17: "COURANTS DÉSÉQUILIBRÉS",
    28: "ENCODEUR",
}


def comm_name(cmd_id: int) -> str:
    return COMM_NAMES.get(cmd_id, f"COMM_{cmd_id}")


# --------------------------------------------------------------------------- CRC16
def _make_table() -> list[int]:
    tab = []
    for i in range(256):
        c = i << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
        tab.append(c)
    return tab


CRC16_TAB = _make_table()  # identique à crc16_tab[] de crc.c (vérifié par les tests)


def crc16(data: bytes, cksum: int = 0) -> int:
    for b in data:
        cksum = CRC16_TAB[((cksum >> 8) ^ b) & 0xFF] ^ ((cksum << 8) & 0xFFFF)
    return cksum


# --------------------------------------------------------------------------- framing
PACKET_MAX_PL_LEN = 512  # packet.h du firmware


def frame_packet(payload: bytes) -> bytes:
    """packet_send_packet() de packet.c."""
    n = len(payload)
    if n == 0 or n > PACKET_MAX_PL_LEN:
        raise ValueError("longueur de charge utile invalide")
    if n <= 255:
        head = bytes([2, n])
    elif n <= 65535:
        head = bytes([3, n >> 8, n & 0xFF])
    else:
        head = bytes([4, n >> 16, (n >> 8) & 0xFF, n & 0xFF])
    c = crc16(payload)
    return head + payload + bytes([c >> 8, c & 0xFF, 3])


@dataclass
class DecodedFrame:
    payload: bytes
    raw: bytes
    crc_rx: int
    crc_calc: int
    ok: bool
    error: str = ""

    @property
    def cmd_id(self) -> int:
        return self.payload[0] if self.payload else -1


class PacketDecoder:
    """Décodeur incrémental équivalent à packet_process_byte()/try_decode_packet()."""

    def __init__(self, max_payload: int = PACKET_MAX_PL_LEN, timeout_s: float = 0.25):
        self.buf = bytearray()
        self.max_payload = max_payload
        self.timeout_s = timeout_s          # trame incomplète abandonnée après ce délai (cf. packet.c)
        self.dropped_bytes = 0
        self._last = time.monotonic()

    def reset(self) -> None:
        self.buf.clear()

    def feed(self, data: bytes) -> list[DecodedFrame]:
        now = time.monotonic()
        if self.buf and self.timeout_s and now - self._last > self.timeout_s:
            self.dropped_bytes += len(self.buf)
            self.buf.clear()
        self._last = now
        self.buf += data
        out: list[DecodedFrame] = []
        while self.buf:
            b0 = self.buf[0]
            if b0 not in (2, 3, 4):
                self.buf.pop(0)
                self.dropped_bytes += 1
                continue
            hl = b0 - 1  # octets de longueur : 1, 2 ou 3
            start = 1 + hl
            if len(self.buf) < start:
                break
            ln = int.from_bytes(self.buf[1:start], "big")
            # un paquet court doit utiliser le plus petit en-tête (cf. packet.c)
            if (b0 == 2 and ln < 1) or (b0 == 3 and ln < 255) or (b0 == 4 and ln < 65535) \
                    or ln > self.max_payload:
                self.buf.pop(0)
                self.dropped_bytes += 1
                continue
            total = start + ln + 3
            if len(self.buf) < total:
                break
            raw = bytes(self.buf[:total])
            payload = raw[start:start + ln]
            crc_rx = (raw[start + ln] << 8) | raw[start + ln + 1]
            crc_calc = crc16(payload)
            if raw[-1] != 3:
                self.buf.pop(0)
                self.dropped_bytes += 1
                out.append(DecodedFrame(payload, raw, crc_rx, crc_calc, False, "octet de fin invalide"))
                continue
            if crc_rx != crc_calc:
                del self.buf[:total]            # trame bien délimitée mais corrompue : on la jette
                self.dropped_bytes += total
                out.append(DecodedFrame(payload, raw, crc_rx, crc_calc, False, "CRC invalide"))
                continue
            del self.buf[:total]
            out.append(DecodedFrame(payload, raw, crc_rx, crc_calc, True))
        return out


# --------------------------------------------------------------------------- buffer.c
def _clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v


def put_i16(b: bytearray, v: float, scale: float = 1.0) -> None:
    b += struct.pack(">h", _clamp(int(v * scale), -32768, 32767))


def put_i32(b: bytearray, v: float, scale: float = 1.0) -> None:
    b += struct.pack(">i", _clamp(int(v * scale), -2**31, 2**31 - 1))


def put_u32(b: bytearray, v: int) -> None:
    b += struct.pack(">I", int(v) & 0xFFFFFFFF)


# (type, échelle)
_T = {"i16": 2, "i32": 4, "u8": 1, "u32": 4}

# Tables (bit, [(nom, type, échelle), ...]) — ordre exact de commands.c
VALUES_SPEC = [
    (0, [("temp_fet", "i16", 1e1)]), (1, [("temp_motor", "i16", 1e1)]),
    (2, [("avg_motor_current", "i32", 1e2)]), (3, [("avg_input_current", "i32", 1e2)]),
    (4, [("avg_id", "i32", 1e2)]), (5, [("avg_iq", "i32", 1e2)]),
    (6, [("duty", "i16", 1e3)]), (7, [("rpm", "i32", 1.0)]),
    (8, [("v_in", "i16", 1e1)]), (9, [("amp_hours", "i32", 1e4)]),
    (10, [("amp_hours_charged", "i32", 1e4)]), (11, [("watt_hours", "i32", 1e4)]),
    (12, [("watt_hours_charged", "i32", 1e4)]), (13, [("tachometer", "i32", 1.0)]),
    (14, [("tachometer_abs", "i32", 1.0)]), (15, [("fault", "u8", 1.0)]),
    (16, [("pid_pos", "i32", 1e6)]), (17, [("controller_id", "u8", 1.0)]),
    (18, [("temp_mos1", "i16", 1e1), ("temp_mos2", "i16", 1e1), ("temp_mos3", "i16", 1e1)]),
    (19, [("avg_vd", "i32", 1e3)]), (20, [("avg_vq", "i32", 1e3)]), (21, [("status", "u8", 1.0)]),
]
SETUP_SPEC = [
    (0, [("temp_fet", "i16", 1e1)]), (1, [("temp_motor", "i16", 1e1)]),
    (2, [("current_tot", "i32", 1e2)]), (3, [("current_in_tot", "i32", 1e2)]),
    (4, [("duty", "i16", 1e3)]), (5, [("rpm", "i32", 1.0)]),
    (6, [("speed", "i32", 1e3)]), (7, [("v_in", "i16", 1e1)]),
    (8, [("battery_level", "i16", 1e3)]), (9, [("amp_hours", "i32", 1e4)]),
    (10, [("amp_hours_charged", "i32", 1e4)]), (11, [("watt_hours", "i32", 1e4)]),
    (12, [("watt_hours_charged", "i32", 1e4)]), (13, [("distance", "i32", 1e3)]),
    (14, [("distance_abs", "i32", 1e3)]), (15, [("pid_pos", "i32", 1e6)]),
    (16, [("fault", "u8", 1.0)]), (17, [("controller_id", "u8", 1.0)]),
    (18, [("num_vescs", "u8", 1.0)]), (19, [("wh_batt_left", "i32", 1e3)]),
    (20, [("odometer", "u32", 1.0)]), (21, [("uptime_ms", "u32", 1.0)]),
]
FULL_MASK = 0xFFFFFFFF


def build_values_payload(cmd_id: int, values: dict, mask: int | None = None) -> bytes:
    """Construit la réponse de COMM_GET_VALUES / _SETUP (+ variantes SELECTIVE si mask != None)."""
    spec = VALUES_SPEC if cmd_id in (COMM_GET_VALUES, COMM_GET_VALUES_SELECTIVE) else SETUP_SPEC
    b = bytearray([cmd_id])
    m = FULL_MASK if mask is None else mask
    if mask is not None:
        put_u32(b, mask)
    for bit, fields in spec:
        if not m & (1 << bit):
            continue
        for name, typ, scale in fields:
            v = values.get(name, 0)
            if typ == "i16":
                put_i16(b, v, scale)
            elif typ == "i32":
                put_i32(b, v, scale)
            elif typ == "u8":
                b.append(int(v) & 0xFF)
            else:
                put_u32(b, int(v))
    return bytes(b)


def parse_values_payload(payload: bytes) -> dict:
    """Décodeur côté client (utilisé par DASHBOARD TEST et les tests)."""
    cmd = payload[0]
    selective = cmd in (COMM_GET_VALUES_SELECTIVE, COMM_GET_VALUES_SETUP_SELECTIVE)
    spec = VALUES_SPEC if cmd in (COMM_GET_VALUES, COMM_GET_VALUES_SELECTIVE) else SETUP_SPEC
    pos = 1
    mask = FULL_MASK
    if selective:
        mask = struct.unpack_from(">I", payload, 1)[0]
        pos = 5
    out: dict = {"_cmd": cmd, "_mask": mask}
    for bit, fields in spec:
        if not mask & (1 << bit):
            continue
        for name, typ, scale in fields:
            size = _T[typ]
            if pos + size > len(payload):
                return out  # firmwares plus anciens : réponse plus courte
            fmt = {"i16": ">h", "i32": ">i", "u8": ">B", "u32": ">I"}[typ]
            raw = struct.unpack_from(fmt, payload, pos)[0]
            pos += size
            out[name] = raw / scale if typ in ("i16", "i32") and scale != 1.0 else raw
    return out


@dataclass
class FwInfo:
    major: int = 7
    minor: int = 1
    hw_name: str = "VESC SIMULATOR"
    fw_name: str = ""
    uuid: bytes = field(default_factory=lambda: bytes(range(0xA0, 0xAC)))
    test_version: int = 0
    hw_crc: int = 0x5EC51A71


def build_fw_version(info: FwInfo) -> bytes:
    """COMM_FW_VERSION — disposition de commands.c (v7.01)."""
    b = bytearray([COMM_FW_VERSION, info.major, info.minor])
    b += info.hw_name.encode() + b"\0"
    b += info.uuid[:12].ljust(12, b"\0")
    b.append(0)                    # pairing_done
    b.append(info.test_version)    # FW_TEST_VERSION_NUMBER
    b.append(0)                    # HW_TYPE_VESC
    b.append(0)                    # custom_cfg_num
    b.append(0)                    # phase filters
    b.append(0)                    # QML HW flags
    b.append(0)                    # QML APP flags
    b.append(0)                    # nrf_flags
    b += info.fw_name.encode() + b"\0"
    put_u32(b, info.hw_crc)
    return bytes(b)


def parse_fw_version(payload: bytes) -> dict:
    major, minor = payload[1], payload[2]
    end = payload.index(0, 3)
    hw = payload[3:end].decode(errors="replace")
    return {"major": major, "minor": minor, "hw_name": hw, "uuid": payload[end + 1:end + 13]}


# trames de requête usuelles (VESC Tool / VescUart)
def request(cmd_id: int, extra: bytes = b"") -> bytes:
    return frame_packet(bytes([cmd_id]) + extra)
