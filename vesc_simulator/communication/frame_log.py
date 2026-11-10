"""Journalisation + statistiques de diagnostic (erreurs CRC, commandes inconnues, pertes, fréquence)."""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

from simulator.paths import app_dir

LOG_DIR = app_dir() / "logs"


@dataclass
class LogEntry:
    ts: float
    direction: str            # RX / TX / INFO / WARN / ERR
    transport: str = ""
    cmd_id: int = -1
    cmd_name: str = ""
    size: int = 0
    crc_calc: int | None = None
    crc_rx: int | None = None
    valid: bool | None = None
    hex: str = ""
    message: str = ""

    @property
    def time_str(self) -> str:
        t = time.localtime(self.ts)
        return time.strftime("%H:%M:%S", t) + f".{int(self.ts * 1000) % 1000:03d}"


class FrameLog:
    def __init__(self, maxlen: int = 5000, to_file: bool = False, log_dir: Path | None = None):
        self.entries: deque[LogEntry] = deque(maxlen=maxlen)
        self.lock = threading.Lock()
        self.listeners: list = []
        self.stats = defaultdict(int)
        self.cmd_count: dict[int, int] = defaultdict(int)
        self.cmd_last_ts: dict[int, float] = {}
        self._intervals: dict[int, deque] = defaultdict(lambda: deque(maxlen=50))
        self._file = None
        if to_file:
            d = Path(log_dir or LOG_DIR)
            d.mkdir(parents=True, exist_ok=True)
            self._file = logging.getLogger(f"vesc_sim_{id(self)}")
            self._file.setLevel(logging.INFO)
            h = logging.FileHandler(d / time.strftime("vesc_%Y%m%d.log"), encoding="utf-8")
            h.setFormatter(logging.Formatter("%(message)s"))
            self._file.addHandler(h)

    def add_listener(self, fn) -> None:
        self.listeners.append(fn)

    def add(self, e: LogEntry) -> LogEntry:
        with self.lock:
            self.entries.append(e)
            self.stats["total"] += 1
            if e.direction == "RX":
                self.stats["rx_frames"] += 1
                self.cmd_count[e.cmd_id] += 1
                prev = self.cmd_last_ts.get(e.cmd_id)
                if prev is not None:
                    self._intervals[e.cmd_id].append(e.ts - prev)
                self.cmd_last_ts[e.cmd_id] = e.ts
                if e.valid is False:
                    self.stats["crc_errors"] += 1
            elif e.direction == "TX":
                self.stats["tx_frames"] += 1
            elif e.direction == "ERR":
                self.stats["errors"] += 1
            elif e.direction == "WARN":
                self.stats["warnings"] += 1
        if self._file:
            self._file.info(f"{e.time_str} {e.direction:4} {e.transport:5} id={e.cmd_id:<3} {e.cmd_name:<28} "
                            f"len={e.size:<4} crc_rx={_h(e.crc_rx)} crc_calc={_h(e.crc_calc)} "
                            f"{'OK' if e.valid else 'KO' if e.valid is False else '--'} {e.hex} {e.message}")
        for fn in list(self.listeners):
            try:
                fn(e)
            except Exception:  # un écouteur ne doit jamais casser la liaison
                pass
        return e

    def info(self, msg: str, direction: str = "INFO", transport: str = "") -> LogEntry:
        return self.add(LogEntry(time.time(), direction, transport, message=msg))

    def count(self, key: str) -> int:
        return self.stats.get(key, 0)

    def rate_hz(self, cmd_id: int) -> float:
        iv = self._intervals.get(cmd_id)
        if not iv:
            return 0.0
        m = sum(iv) / len(iv)
        return 1.0 / m if m > 0 else 0.0

    def seconds_since(self, cmd_id: int | None = None) -> float | None:
        if cmd_id is None:
            ts = max(self.cmd_last_ts.values(), default=None)
        else:
            ts = self.cmd_last_ts.get(cmd_id)
        return None if ts is None else time.time() - ts

    def check_refresh(self, cmd_id: int, min_hz: float = 2.0) -> str | None:
        """Retourne un message si la fréquence d'interrogation est anormale."""
        hz = self.rate_hz(cmd_id)
        if hz and hz < min_hz:
            return f"Fréquence de rafraîchissement faible : {hz:.1f} Hz"
        return None

    def clear(self) -> None:
        with self.lock:
            self.entries.clear()
            self.stats.clear()
            self.cmd_count.clear()
            self.cmd_last_ts.clear()
            self._intervals.clear()


def _h(v) -> str:
    return "----" if v is None else f"{v:04X}"
