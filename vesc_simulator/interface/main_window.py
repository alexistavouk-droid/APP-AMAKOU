"""Fenêtre principale VESC SIMULATOR PRO."""
from __future__ import annotations

import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QMainWindow, QPushButton, QTabWidget, QVBoxLayout,
                               QWidget)

from communication import vesc_protocol as P
from interface import theme
from interface.comm_panel import CommTab, ScenariosTab
from interface.context import AppContext
from interface.dashboard import DashboardTab
from interface.diagnostics import DashboardTestTab, DiagnosticsTab
from interface.settings import SettingsTab

SPEEDS = [("Ralenti ×0,25", 0.25), ("Normal ×1", 1.0), ("Accéléré ×4", 4.0)]


def pill(text="—"):
    l = QLabel(text); l.setObjectName("pill"); return l


def set_pill(l: QLabel, text: str, color: str) -> None:
    l.setText(text)
    l.setStyleSheet(f"color:{color};")


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext | None = None):
        super().__init__()
        self.ctx = ctx or AppContext()
        self.setWindowTitle("VESC SIMULATOR PRO")
        self.resize(1360, 860)
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # --- barre d'état
        bar = QHBoxLayout()
        self.p_vesc, self.p_sim, self.p_conn = pill(), pill(), pill()
        self.p_port, self.p_bt, self.p_hz, self.p_time = pill(), pill(), pill(), pill()
        for lab, w in [("VESC", self.p_vesc), ("Simulation", self.p_sim), ("Connexion", self.p_conn),
                       ("Port", self.p_port), ("BLE", self.p_bt), ("Requêtes", self.p_hz), ("Temps simulé", self.p_time)]:
            l = QLabel(lab); l.setObjectName("tileTitle"); bar.addWidget(l); bar.addWidget(w)
        bar.addStretch()
        root.addLayout(bar)

        # --- commandes
        cmd = QHBoxLayout()
        self.b_start = QPushButton("▶ START SIMULATION"); self.b_start.setObjectName("start")
        self.b_stop = QPushButton("■ STOP SIMULATION"); self.b_stop.setObjectName("stop")
        self.b_pause = QPushButton("⏸ PAUSE"); self.b_reset = QPushButton("↺ RESET")
        self.speed = QComboBox()
        for n, v in SPEEDS:
            self.speed.addItem(n, v)
        self.speed.setCurrentIndex(1)
        self.b_start.clicked.connect(self.start_sim); self.b_stop.clicked.connect(self.stop_sim)
        self.b_pause.clicked.connect(self.toggle_pause); self.b_reset.clicked.connect(self.reset_sim)
        self.speed.currentIndexChanged.connect(lambda _: setattr(self.ctx.engine, "time_scale", self.speed.currentData()))
        for w in (self.b_start, self.b_stop, self.b_pause, self.b_reset, QLabel("Mode :"), self.speed):
            cmd.addWidget(w)
        cmd.addStretch()
        root.addLayout(cmd)

        # --- onglets
        self.tabs = QTabWidget()
        self.dash = DashboardTab(self.ctx)
        self.scen = ScenariosTab(self.ctx, self.start_sim)
        self.sett = SettingsTab(self.ctx, self.on_config)
        self.comm = CommTab(self.ctx)
        self.diag = DiagnosticsTab(self.ctx)
        self.dtest = DashboardTestTab(self.ctx)
        for w, n in [(self.dash, "Tableau de bord"), (self.scen, "Scénarios"), (self.sett, "Réglages et profils"),
                     (self.comm, "Communication"), (self.diag, "Diagnostic"), (self.dtest, "DASHBOARD TEST")]:
            self.tabs.addTab(w, n)
        root.addWidget(self.tabs, 1)

        self.timer = QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(100)
        self._tick_n = 0

    # --- actions
    def start_sim(self):
        self.ctx.engine.start()

    def stop_sim(self):
        self.ctx.engine.stop()

    def toggle_pause(self):
        e = self.ctx.engine
        e.pause(not e.paused)
        self.b_pause.setText("▶ REPRENDRE" if e.paused else "⏸ PAUSE")

    def reset_sim(self):
        e = self.ctx.engine
        e.set_scenario(None)
        e.reset_state()
        self.dash.release_all(); self.dash.clear_charts(); self.dash.on_config()
        e.set_soc(self.dash.soc.value() / 10)

    def on_config(self):
        self.dash.on_config(); self.dash.clear_charts()

    # --- rafraîchissement
    def tick(self):
        c = self.ctx
        e = c.engine
        now = time.time()
        t = e.snapshot()
        self.dash.refresh(t, now)
        since = c.log.seconds_since()
        linked = since is not None and since < 3.0 and e.link.link_up
        set_pill(self.p_vesc, "CONNECTÉ" if linked else "DÉCONNECTÉ", theme.OK if linked else theme.BAD)
        if not e.running:
            set_pill(self.p_sim, "STOPPED", theme.BAD)
        elif e.paused:
            set_pill(self.p_sim, "PAUSE", theme.WARN)
        else:
            set_pill(self.p_sim, "RUNNING", theme.OK)
        tr = c.transport if (c.uart.connected or c.virtual.running or c.can or (c.ble and c.ble.running)) else "—"
        self.p_conn.setText(tr)
        self.p_port.setText(f"{c.uart.port} @ {c.uart.baud}" if c.uart.connected else "—")
        self.p_bt.setText(c.ble_address or ("actif" if c.ble and c.ble.running else "—"))
        hz = c.log.rate_hz(P.COMM_GET_VALUES) or c.log.rate_hz(P.COMM_GET_VALUES_SETUP)
        self.p_hz.setText(f"{hz:.1f} Hz")
        self.p_time.setText(time.strftime("%H:%M:%S", time.gmtime(e.t)))
        self.scen.refresh()
        self.diag.refresh()
        self._tick_n += 1
        if self.tabs.currentWidget() is self.dtest and self._tick_n % 3 == 0:
            self.dtest.refresh()

    def closeEvent(self, ev):
        self.timer.stop()
        self.ctx.shutdown()
        super().closeEvent(ev)
