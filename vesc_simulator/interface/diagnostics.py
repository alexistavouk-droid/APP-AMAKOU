"""Diagnostic : trames, journal, statistiques + onglet DASHBOARD TEST."""
from __future__ import annotations

import queue
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from communication import vesc_protocol as P
from interface import theme

MAX_ROWS = 1500
STATUS_COLOR = {"OK": theme.OK, "ATTENTE": theme.WARN, "ÉCHEC": theme.BAD, "MANUEL": theme.ACCENT}


def _item(text, color=None):
    it = QTableWidgetItem(str(text))
    if color:
        it.setForeground(QBrush(QColor(color)))
    return it


class DiagnosticsTab(QWidget):
    COLS = ["Heure", "Sens", "Transport", "ID", "Commande", "Taille", "CRC calculé", "CRC reçu", "Validation", "Trame (hex)"]

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.q: queue.Queue = queue.Queue()
        ctx.log.add_listener(self.q.put)
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.only_err = QCheckBox("Erreurs / alertes seulement")
        self.pause = QCheckBox("Geler l'affichage")
        b_clear = QPushButton("Effacer"); b_clear.clicked.connect(self.clear)
        b_exp = QPushButton("Exporter…"); b_exp.clicked.connect(self.export)
        self.stats = QLabel()
        for w in (self.only_err, self.pause, b_clear, b_exp):
            bar.addWidget(w)
        bar.addStretch(); bar.addWidget(self.stats)
        root.addLayout(bar)
        split = QSplitter(Qt.Vertical)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        for i, w in enumerate([90, 50, 80, 40, 210, 60, 90, 80, 90]):
            self.table.setColumnWidth(i, w)
        split.addWidget(self.table)
        self.journal = QPlainTextEdit(); self.journal.setReadOnly(True); self.journal.setMaximumBlockCount(2000)
        split.addWidget(self.journal)
        split.setSizes([420, 160])
        root.addWidget(split, 1)

    def clear(self):
        self.table.setRowCount(0); self.journal.clear(); self.ctx.log.clear()

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exporter le journal", "vesc_log.txt", "Texte (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                for e in list(self.ctx.log.entries):
                    f.write(f"{e.time_str}\t{e.direction}\t{e.transport}\t{e.cmd_id}\t{e.cmd_name}\t{e.size}\t"
                            f"{e.crc_calc}\t{e.crc_rx}\t{e.valid}\t{e.hex}\t{e.message}\n")

    def refresh(self):
        n = 0
        while n < 200:
            try:
                e = self.q.get_nowait()
            except queue.Empty:
                break
            n += 1
            if self.pause.isChecked():
                continue
            if e.direction in ("RX", "TX"):
                if self.only_err.isChecked() and e.valid is not False:
                    continue
                r = self.table.rowCount()
                self.table.insertRow(r)
                ok = e.valid
                col = theme.OK if ok else theme.BAD if ok is False else None
                vals = [e.time_str, e.direction, e.transport, e.cmd_id, e.cmd_name, e.size,
                        f"{e.crc_calc:04X}" if e.crc_calc is not None else "—",
                        f"{e.crc_rx:04X}" if e.crc_rx is not None else "—",
                        "VALIDE" if ok else "CRC INVALIDE" if ok is False else "—", e.hex]
                for c, v in enumerate(vals):
                    self.table.setItem(r, c, _item(v, (theme.ACCENT if e.direction == "TX" else None) if c == 1
                                                   else col if c == 8 else None))
                if self.table.rowCount() > MAX_ROWS:
                    self.table.removeRow(0)
                self.table.scrollToBottom()
            else:
                color = {"ERR": theme.BAD, "WARN": theme.WARN}.get(e.direction, theme.MUTED)
                self.journal.appendHtml(f'<span style="color:{color}">{e.time_str} [{e.direction}] '
                                        f'{e.transport} {e.message}</span>')
        lg = self.ctx.log
        hz = lg.rate_hz(P.COMM_GET_VALUES) or lg.rate_hz(P.COMM_GET_VALUES_SETUP)
        self.stats.setText(f"RX {lg.count('rx_frames')} · TX {lg.count('tx_frames')} · erreurs CRC {lg.count('crc_errors')}"
                           f" · inconnues {lg.count('unknown_cmds')} · bloquées {lg.count('blocked_cmds')}"
                           f" · octets perdus {self.ctx.responder.decoder.dropped_bytes} · {hz:.1f} Hz")
        warn = lg.check_refresh(P.COMM_GET_VALUES) or lg.check_refresh(P.COMM_GET_VALUES_SETUP)
        if warn and not getattr(self, "_warned", False):
            lg.info(warn, "WARN"); self._warned = True
        elif not warn:
            self._warned = False


class DashboardTestTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        g = QGroupBox("Vérifications automatiques (côté ESP32)")
        gl = QVBoxLayout(g)
        self.checks = QTableWidget(0, 3)
        self.checks.setHorizontalHeaderLabels(["Test", "État", "Détail"])
        self.checks.verticalHeader().setVisible(False)
        self.checks.setEditTriggers(QTableWidget.NoEditTriggers)
        self.checks.setColumnWidth(0, 190); self.checks.setColumnWidth(1, 80)
        self.checks.horizontalHeader().setStretchLastSection(True)
        gl.addWidget(self.checks)
        left.addWidget(g, 3)
        gb = QGroupBox("Reçu de l'ESP32"); bl = QVBoxLayout(gb)
        self.rx = QPlainTextEdit(); self.rx.setReadOnly(True); bl.addWidget(self.rx)
        left.addWidget(gb, 2)
        root.addLayout(left, 3)

        right = QVBoxLayout()
        gs = QGroupBox("Envoyé par le simulateur — à comparer avec l'écran"); sl = QVBoxLayout(gs)
        self.sent = QTableWidget(0, 3)
        self.sent.setHorizontalHeaderLabels(["Paramètre", "Valeur simulateur", "Codé dans la trame"])
        self.sent.verticalHeader().setVisible(False)
        self.sent.setEditTriggers(QTableWidget.NoEditTriggers)
        self.sent.setColumnWidth(0, 200); self.sent.setColumnWidth(1, 130)
        self.sent.horizontalHeader().setStretchLastSection(True)
        sl.addWidget(self.sent)
        right.addWidget(gs, 3)
        ga = QGroupBox("Actions"); al = QGridLayout(ga)
        b1 = QPushButton("Appliquer le vecteur de référence"); b1.setObjectName("primary")
        b1.clicked.connect(ctx.tester.apply_reference_vector)
        b2 = QPushButton("Libérer"); b2.clicked.connect(ctx.tester.release)
        b3 = QPushButton("Test déconnexion (6 s)"); b3.clicked.connect(lambda: ctx.tester.start_link_test(6.0))
        self.fault_cb = QComboBox()
        for label, code in [("Défaut : aucun", 0), ("Surtension", 1), ("Sous-tension", 2),
                            ("Surchauffe MOSFET", 5), ("Surintensité", 4), ("Erreur moteur", 17)]:
            self.fault_cb.addItem(label, code)
        self.fault_cb.currentIndexChanged.connect(lambda _: ctx.engine.set_fault(self.fault_cb.currentData()))
        hint = QLabel("Vecteur de référence : 500 tr/min méca., 48,0 V, 10,0 A, moteur 55 °C, MOSFET 40 °C, "
                      "batterie 50 %. Relever ces valeurs sur l'écran du tableau de bord.")
        hint.setWordWrap(True); hint.setObjectName("tileUnit")
        al.addWidget(b1, 0, 0); al.addWidget(b2, 0, 1); al.addWidget(b3, 1, 0); al.addWidget(self.fault_cb, 1, 1)
        al.addWidget(hint, 2, 0, 1, 2)
        right.addWidget(ga, 1)
        root.addLayout(right, 3)

    def refresh(self):
        t = self.ctx.tester
        t.tick()
        res = t.checks()
        self.checks.setRowCount(len(res))
        for i, c in enumerate(res):
            self.checks.setItem(i, 0, _item(c.name))
            self.checks.setItem(i, 1, _item(c.status, STATUS_COLOR.get(c.status)))
            self.checks.setItem(i, 2, _item(c.detail))
        rows = t.sent_table()
        self.sent.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, v in enumerate(r):
                self.sent.setItem(i, j, _item(v))
        lg = self.ctx.log
        lines = []
        for cid, n in sorted(lg.cmd_count.items()):
            age = time.time() - lg.cmd_last_ts[cid]
            lines.append(f"{P.comm_name(cid):<34} x{n:<6} {lg.rate_hz(cid):5.1f} Hz   (il y a {age:4.1f} s)")
        self.rx.setPlainText("\n".join(lines) or "Aucune requête reçue.")
