"""Onglets Communication (UART / BLE / CAN) et Scénarios."""
from __future__ import annotations

import asyncio
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QMessageBox, QProgressBar, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from communication import vesc_protocol as P
from communication.uart_server import DEFAULT_BAUD, list_ports
from simulator.scenarios import SCENARIOS, make_scenario

BAUDS = ["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"]


class CommTab(QWidget):
    scan_done = Signal(object)

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        root = QVBoxLayout(self)
        note = QLabel("🔒 Mode TÉLÉMÉTRIE SEULE : seules les commandes de lecture sont traitées. Toute commande de "
                      "pilotage, configuration ou mise à jour (SET_*, REBOOT, bootloader…) est journalisée et ignorée.")
        note.setWordWrap(True); note.setObjectName("tileUnit")
        root.addWidget(note)

        # ---- UART
        g = QGroupBox("UART / USB (port COM)"); f = QFormLayout(g)
        self.port = QComboBox(); self.port.setEditable(True); self.port.setMinimumWidth(260)
        b_ref = QPushButton("Actualiser"); b_ref.clicked.connect(self.refresh_ports)
        row = QHBoxLayout(); row.addWidget(self.port, 1); row.addWidget(b_ref)
        self.baud = QComboBox(); self.baud.setEditable(True); self.baud.addItems(BAUDS)
        self.baud.setCurrentText(str(DEFAULT_BAUD))
        self.btn = QPushButton("Connecter"); self.btn.setObjectName("primary"); self.btn.clicked.connect(self.toggle_uart)
        self.status = QLabel("Déconnecté")
        self.push = QCheckBox("Envoi périodique non sollicité de COMM_GET_VALUES"); self.push_hz = QDoubleSpinBox()
        self.push_hz.setRange(1, 100); self.push_hz.setValue(10); self.push_hz.setSuffix(" Hz")
        self.push.toggled.connect(self.on_push)
        pr = QHBoxLayout(); pr.addWidget(self.push); pr.addWidget(self.push_hz)
        f.addRow("Port COM", row); f.addRow("Débit (bauds)", self.baud); f.addRow(self.btn, self.status); f.addRow(pr)
        root.addWidget(g)

        # ---- virtuel
        gv = QGroupBox("ESP32 virtuel (test sans matériel)"); vl = QHBoxLayout(gv)
        self.vbtn = QPushButton("Démarrer l'ESP32 virtuel"); self.vbtn.clicked.connect(self.toggle_virtual)
        vl.addWidget(self.vbtn); vl.addWidget(QLabel("Interroge le simulateur en boucle locale, comme un vrai tableau de bord (10 Hz)."))
        vl.addStretch()
        root.addWidget(gv)

        # ---- BLE
        gb = QGroupBox("Bluetooth BLE (Nordic UART Service)"); bl = QVBoxLayout(gb)
        self.ble_lbl = QLabel("Service 6E400001-B5A3-F393-E0A9-E50E24DCCA9E — RX …0002 (écriture) / TX …0003 (notifications)\n"
                              "Serveur GATT natif : expérimental (Windows 10/11, paquets winrt). Alternative fiable : pont ESP32 BLE↔UART "
                              "(voir docs/BLUETOOTH.md).")
        self.ble_lbl.setWordWrap(True); self.ble_lbl.setObjectName("tileUnit")
        hb = QHBoxLayout()
        self.ble_btn = QPushButton("Démarrer serveur BLE"); self.ble_btn.clicked.connect(self.toggle_ble)
        self.scan_btn = QPushButton("Scanner les périphériques BLE"); self.scan_btn.clicked.connect(self.scan_ble)
        hb.addWidget(self.ble_btn); hb.addWidget(self.scan_btn); hb.addStretch()
        self.ble_list = QListWidget(); self.ble_list.setMaximumHeight(90)
        bl.addWidget(self.ble_lbl); bl.addLayout(hb); bl.addWidget(self.ble_list)
        root.addWidget(gb)
        self.scan_done.connect(self._scan_result)

        # ---- CAN
        gc = QGroupBox("CAN Bus (extension, python-can)"); cl = QHBoxLayout(gc)
        self.can_if = QComboBox(); self.can_if.addItems(["virtual", "slcan", "socketcan", "pcan", "kvaser", "gs_usb"])
        self.can_ch = QLineEdit("vesc_sim"); self.can_node = QSpinBox(); self.can_node.setRange(0, 254)
        self.can_btn = QPushButton("Démarrer CAN"); self.can_btn.clicked.connect(self.toggle_can)
        for w in (QLabel("Interface"), self.can_if, QLabel("Canal"), self.can_ch, QLabel("ID nœud"), self.can_node, self.can_btn):
            cl.addWidget(w)
        root.addWidget(gc)
        root.addStretch()
        self.refresh_ports()

    # ---- UART
    def refresh_ports(self):
        cur = self.port.currentText()
        self.port.clear()
        for dev, desc in list_ports():
            self.port.addItem(dev, dev)
            self.port.setItemData(self.port.count() - 1, desc, Qt.ToolTipRole)
        self.port.setCurrentText(cur)

    def toggle_uart(self):
        u = ctx = self.ctx.uart
        if u.connected:
            u.stop(); self.btn.setText("Connecter"); self.status.setText("Déconnecté"); self.ctx.transport = "—"
            return
        try:
            u.start(self.port.currentText().strip(), int(self.baud.currentText()))
        except Exception as exc:
            QMessageBox.critical(self, "Port série", f"Ouverture impossible : {exc}")
            return
        self.on_push(self.push.isChecked())
        self.btn.setText("Déconnecter"); self.status.setText(f"Connecté {u.port} @ {u.baud}")
        self.ctx.transport = "UART"

    def on_push(self, on):
        self.ctx.uart.set_push(self.push_hz.value() if on else 0.0, P.COMM_GET_VALUES)

    def toggle_virtual(self):
        v = self.ctx.virtual
        if v.running:
            v.stop(); self.vbtn.setText("Démarrer l'ESP32 virtuel")
        else:
            v.start(); self.vbtn.setText("Arrêter l'ESP32 virtuel")
            if self.ctx.transport == "—":
                self.ctx.transport = "VIRTUEL"

    # ---- BLE
    def toggle_ble(self):
        from communication.ble_server import WinRtBleServer
        c = self.ctx
        if c.ble and c.ble.running:
            c.ble.stop(); self.ble_btn.setText("Démarrer serveur BLE"); return
        if not WinRtBleServer.available():
            QMessageBox.information(self, "BLE", "Serveur GATT WinRT indisponible sur ce système.\n"
                                    "Voir docs/BLUETOOTH.md (pont ESP32 BLE↔UART).")
            return
        from communication.responder import VescResponder
        c.ble = WinRtBleServer(VescResponder(c.engine, c.log, "BLE"))
        try:
            c.ble.start()
            self.ble_btn.setText("Arrêter serveur BLE"); c.transport = "BLE"
        except Exception as exc:
            QMessageBox.warning(self, "BLE", str(exc))

    def scan_ble(self):
        self.scan_btn.setEnabled(False); self.ble_list.clear(); self.ble_list.addItem("Scan en cours (5 s)…")

        def run():
            try:
                from communication.ble_server import scan
                res = asyncio.run(scan(5.0))
            except Exception as exc:
                res = str(exc)
            self.scan_done.emit(res)
        threading.Thread(target=run, daemon=True).start()

    def _scan_result(self, res):
        self.scan_btn.setEnabled(True); self.ble_list.clear()
        if isinstance(res, str):
            self.ble_list.addItem(f"Erreur : {res}"); return
        for addr, name, uuids in sorted(res, key=lambda r: r[1] == ""):
            nus = " ★ NUS" if any(u.lower().startswith("6e400001") for u in uuids) else ""
            self.ble_list.addItem(f"{addr}  {name or '(sans nom)'}{nus}")
            if nus and not self.ctx.ble_address:
                self.ctx.ble_address = addr

    # ---- CAN
    def toggle_can(self):
        from communication.can_interface import CanInterface
        c = self.ctx
        if c.can:
            c.can.stop(); c.can = None; self.can_btn.setText("Démarrer CAN"); return
        try:
            c.can = CanInterface(c.engine, c.log)
            c.can.start(self.can_if.currentText(), self.can_ch.text(), node_id=self.can_node.value())
            self.can_btn.setText("Arrêter CAN"); c.transport = "CAN"
        except Exception as exc:
            c.can = None
            QMessageBox.warning(self, "CAN", f"Impossible de démarrer le CAN : {exc}")


class ScenariosTab(QWidget):
    def __init__(self, ctx, on_start):
        super().__init__()
        self.ctx, self.on_start = ctx, on_start
        root = QHBoxLayout(self)
        self.list = QListWidget()
        for cls in SCENARIOS:
            self.list.addItem(f"{cls.id}. {cls.name}")
        self.list.currentRowChanged.connect(self._sel)
        root.addWidget(self.list, 1)
        right = QVBoxLayout()
        self.desc = QLabel("Sélectionnez un scénario."); self.desc.setWordWrap(True); self.desc.setAlignment(Qt.AlignTop)
        self.bar = QProgressBar(); self.bar.setRange(0, 100)
        self.cur = QLabel("")
        run = QPushButton("▶ Lancer le scénario"); run.setObjectName("start"); run.clicked.connect(self.run)
        stop = QPushButton("■ Arrêter le scénario"); stop.setObjectName("stop"); stop.clicked.connect(self.stop)
        for w in (self.desc, self.cur, self.bar, run, stop):
            right.addWidget(w)
        right.addStretch()
        root.addLayout(right, 2)
        self.list.setCurrentRow(0)

    def _sel(self, i):
        if i >= 0:
            cls = SCENARIOS[i]
            self.desc.setText(f"<h3>{cls.id}. {cls.name}</h3><p>{cls.description}</p><p>Durée ≈ {cls.duration:.0f} s "
                              f"(temps simulé).</p>")

    def run(self):
        i = self.list.currentRow()
        if i >= 0:
            self.on_start()
            self.ctx.engine.set_scenario(make_scenario(SCENARIOS[i].id))

    def stop(self):
        self.ctx.engine.set_scenario(None)
        self.ctx.engine.link.link_up = True
        self.ctx.engine.link.drop_rate = self.ctx.engine.link.crc_corrupt_rate = 0.0

    def refresh(self):
        sc = self.ctx.engine.scenario
        if sc is None:
            self.bar.setValue(0); self.cur.setText("Aucun scénario actif")
        else:
            t = self.ctx.engine.t - sc.t0
            self.bar.setValue(int(100 * min(1.0, t / sc.duration)))
            extra = f" — {sc.current}" if hasattr(sc, "current") else ""
            self.cur.setText(f"En cours : {sc.name} ({t:.0f}/{sc.duration:.0f} s){extra}")
