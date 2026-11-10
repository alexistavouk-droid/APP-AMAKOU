"""Répondeur VESC indépendant du transport (UART, BLE, tests) : requête → trame(s) de réponse."""
from __future__ import annotations

import random
import struct
import time

from communication import vesc_protocol as P
from communication.frame_log import FrameLog, LogEntry


class VescResponder:
    def __init__(self, engine, log: FrameLog | None = None, transport: str = "UART"):
        self.engine = engine
        self.log = log or FrameLog()
        self.transport = transport
        self.decoder = P.PacketDecoder()
        self.rng = random.Random()

    # ------------------------------------------------------------------ API
    def feed(self, data: bytes) -> list[bytes]:
        """Octets reçus → liste de trames complètes à renvoyer."""
        out: list[bytes] = []
        before = self.decoder.dropped_bytes
        for fr in self.decoder.feed(data):
            out += self.handle_frame(fr)
        skipped = self.decoder.dropped_bytes - before
        if skipped and not out:
            pass
        return out

    def handle_frame(self, fr: P.DecodedFrame) -> list[bytes]:
        now = time.time()
        cid = fr.cmd_id
        self.log.add(LogEntry(now, "RX", self.transport, cid, P.comm_name(cid), len(fr.payload),
                              fr.crc_calc, fr.crc_rx, fr.ok, fr.raw.hex(" "),
                              "" if fr.ok else fr.error))
        if not fr.ok:
            self.log.add(LogEntry(now, "ERR", self.transport, message=f"Erreur CRC : reçu {fr.crc_rx:04X}, "
                                                                          f"calculé {fr.crc_calc:04X}"))
            return []
        link = self.engine.link
        if not link.link_up:
            self.log.info("Liaison coupée (simulation) : requête ignorée", "WARN", self.transport)
            return []
        if link.drop_rate and self.rng.random() < link.drop_rate:
            self.log.info("Défaut de communication simulé : réponse perdue", "WARN", self.transport)
            return []
        reply = self.process_payload(fr.payload)
        if reply is None:
            return []
        frame = P.frame_packet(reply)
        if link.crc_corrupt_rate and self.rng.random() < link.crc_corrupt_rate:
            frame = frame[:-2] + bytes([frame[-2] ^ 0xFF, frame[-1]])
            self.log.info("Défaut simulé : CRC de la réponse corrompu", "WARN", self.transport)
        if link.reply_delay_ms:
            time.sleep(link.reply_delay_ms / 1000.0)
        self.log.add(LogEntry(time.time(), "TX", self.transport, reply[0], P.comm_name(reply[0]),
                              len(reply), P.crc16(reply), P.crc16(reply), True, frame.hex(" ")))
        return [frame]

    # ------------------------------------------------------------------ commandes
    def process_payload(self, payload: bytes) -> bytes | None:
        cid, data = payload[0], payload[1:]
        eng = self.engine
        if cid == P.COMM_FORWARD_CAN:
            if not data:
                return None
            if data[0] != eng.cfg.controller_id:
                self.log.info(f"COMM_FORWARD_CAN vers le nœud {data[0]} : ignoré (nœud simulé = "
                              f"{eng.cfg.controller_id})", "INFO", self.transport)
                return None
            return self.process_payload(data[1:]) if len(data) > 1 else None
        if cid == P.COMM_FW_VERSION:
            c = eng.cfg
            return P.build_fw_version(P.FwInfo(c.fw_major, c.fw_minor, c.hw_name))
        if cid in (P.COMM_GET_VALUES, P.COMM_GET_VALUES_SETUP):
            return self._values(cid, None)
        if cid in (P.COMM_GET_VALUES_SELECTIVE, P.COMM_GET_VALUES_SETUP_SELECTIVE):
            if len(data) < 4:
                self.log.info("Requête SELECTIVE sans masque (4 octets)", "ERR", self.transport)
                return None
            return self._values(cid, struct.unpack(">I", data[:4])[0])
        if cid == P.COMM_PING_CAN:
            return bytes([P.COMM_PING_CAN])          # aucun nœud CAN esclave simulé
        if cid in P.PASSIVE_COMMANDS:
            return None                               # COMM_ALIVE : pas de réponse (comme le firmware)
        if cid in P.BLOCKED_COMMANDS:
            self.log.info(f"{P.comm_name(cid)} BLOQUÉE : simulateur en télémétrie seule "
                          f"(commande de pilotage/configuration)", "WARN", self.transport)
            self.log.stats["blocked_cmds"] += 1
            return None
        if cid in P.UNSUPPORTED_READ_COMMANDS:
            self.log.info(f"{P.comm_name(cid)} : lecture non émulée (aucune structure inventée)",
                          "WARN", self.transport)
            self.log.stats["unsupported_cmds"] += 1
            return None
        self.log.info(f"Commande non reconnue : id={cid}", "WARN", self.transport)
        self.log.stats["unknown_cmds"] += 1
        return None

    def _values(self, cid: int, mask: int | None) -> bytes:
        tel = self.engine.snapshot()
        vals = tel.vesc_values() if cid in (P.COMM_GET_VALUES, P.COMM_GET_VALUES_SELECTIVE) \
            else tel.vesc_setup_values()
        return P.build_values_payload(cid, vals, mask)
