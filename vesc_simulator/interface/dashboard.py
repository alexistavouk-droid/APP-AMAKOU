"""Onglet tableau de bord : télémétrie temps réel, curseurs de forçage, graphiques."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
                               QSlider, QVBoxLayout, QWidget)

from communication import vesc_protocol as P
from interface import theme
from interface.charts import LineChart

TILES = [  # clé, titre, unité, format, couleur d'alerte (fn)
    ("rpm_mech", "RPM moteur", "tr/min", "{:.0f}"), ("speed_kmh", "Vitesse véhicule", "km/h", "{:.1f}"),
    ("v_in", "Tension batterie", "V", "{:.1f}"), ("i_batt", "Courant batterie", "A", "{:+.1f}"),
    ("i_motor", "Courant moteur", "A", "{:+.1f}"), ("power_w", "Puissance", "W", "{:+.0f}"),
    ("temp_fet", "Température MOSFET", "°C", "{:.1f}"), ("temp_motor", "Température moteur", "°C", "{:.1f}"),
    ("soc_pct", "Niveau batterie", "%", "{:.1f}"), ("wh_per_km", "Consommation", "Wh/km", "{:.1f}"),
    ("distance_km", "Distance parcourue", "km", "{:.3f}"), ("wh_used", "Wh consommés", "Wh", "{:.2f}"),
]


def _alert(key: str, v: float) -> str:
    if key in ("temp_fet", "temp_motor"):
        return theme.BAD if v >= 100 else theme.WARN if v >= 80 else theme.TEXT
    if key == "soc_pct":
        return theme.BAD if v <= 10 else theme.WARN if v <= 20 else theme.TEXT
    if key in ("i_batt", "power_w"):
        return theme.OK if v < -0.5 else theme.TEXT
    return theme.TEXT


class Tile(QFrame):
    def __init__(self, title, unit):
        super().__init__()
        self.setObjectName("tile")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(0)
        t = QLabel(title.upper()); t.setObjectName("tileTitle")
        self.value = QLabel("—"); self.value.setObjectName("tileValue")
        u = QLabel(unit); u.setObjectName("tileUnit")
        row = QHBoxLayout(); row.addWidget(self.value); row.addWidget(u, 0, Qt.AlignBottom); row.addStretch()
        lay.addWidget(t); lay.addLayout(row)

    def set(self, text: str, color: str) -> None:
        self.value.setText(text)
        self.value.setStyleSheet(f"color:{color};")


class OverrideSlider(QWidget):
    """Curseur de forçage : actif => la valeur est imposée au simulateur et transmise à l'ESP32."""

    def __init__(self, label, unit, lo, hi, init, on_change, on_release, scale=1.0):
        super().__init__()
        self.scale, self.on_change, self.on_release = scale, on_change, on_release
        lay = QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        self.chk = QCheckBox(label); self.chk.setMinimumWidth(130)
        self.sl = QSlider(Qt.Horizontal); self.sl.setRange(int(lo * scale), int(hi * scale))
        self.sl.setValue(int(init * scale))
        self.val = QLabel(); self.val.setMinimumWidth(80); self.unit = unit
        lay.addWidget(self.chk); lay.addWidget(self.sl, 1); lay.addWidget(self.val)
        self.sl.valueChanged.connect(self._moved)
        self.chk.toggled.connect(self._toggled)
        self._refresh_label()

    def set_range(self, lo, hi, init):
        self.sl.blockSignals(True)
        self.sl.setRange(int(lo * self.scale), int(hi * self.scale)); self.sl.setValue(int(init * self.scale))
        self.sl.blockSignals(False)
        self._refresh_label()

    def value(self) -> float:
        return self.sl.value() / self.scale

    def _refresh_label(self):
        self.val.setText(f"{self.value():.1f} {self.unit}")

    def _moved(self, _):
        self._refresh_label()
        if not self.chk.isChecked():
            self.chk.setChecked(True)      # déclenche _toggled => applique
        else:
            self.on_change(self.value())

    def _toggled(self, on):
        self.on_change(self.value()) if on else self.on_release()

    def release(self):
        self.chk.blockSignals(True); self.chk.setChecked(False); self.chk.blockSignals(False)
        self.on_release()


class DashboardTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        eng = ctx.engine
        root = QVBoxLayout(self)
        self.fault = QLabel(""); self.fault.setAlignment(Qt.AlignCenter)
        self.fault.setStyleSheet(f"background:{theme.BAD};border-radius:6px;padding:6px;font-weight:700;")
        self.fault.hide()
        root.addWidget(self.fault)
        grid = QGridLayout(); grid.setSpacing(8)
        self.tiles = {}
        for i, (k, title, unit, _f) in enumerate(TILES):
            self.tiles[k] = Tile(title, unit)
            grid.addWidget(self.tiles[k], i // 6, i % 6)
        root.addLayout(grid)
        self.thermal = QLabel(); self.thermal.setObjectName("tileUnit")
        root.addWidget(self.thermal)

        mid = QHBoxLayout()
        charts = QGridLayout(); charts.setSpacing(8)
        self.c_rpm = LineChart("RPM moteur", "tr/min", ["rpm"])
        self.c_spd = LineChart("Vitesse", "km/h", ["vitesse"])
        self.c_v = LineChart("Tension batterie", "V", ["V"])
        self.c_i = LineChart("Intensité", "A", ["batterie", "moteur"])
        self.c_p = LineChart("Puissance", "W", ["W"])
        self.c_t = LineChart("Températures", "°C", ["moteur", "MOSFET"])
        for i, c in enumerate([self.c_rpm, self.c_spd, self.c_v, self.c_i, self.c_p, self.c_t]):
            charts.addWidget(c, i // 3, i % 3)
        mid.addLayout(charts, 3)

        box = QGroupBox("Forçage en direct (transmis immédiatement à l'ESP32)")
        bl = QVBoxLayout(box)
        c = eng.cfg
        self.sliders = {
            "rpm": OverrideSlider("RPM moteur", "tr/min", 0, 1500, 300,
                                  lambda v: eng.set_override("rpm", v), lambda: eng.clear_override("rpm")),
            "speed": OverrideSlider("Vitesse", "km/h", 0, 80, 25,
                                    lambda v: eng.set_override("speed", v), lambda: eng.clear_override("speed")),
            "v_in": OverrideSlider("Tension batterie", "V", c.min_v * 0.8, c.max_v * 1.15, c.nominal_v,
                                   lambda v: eng.set_override("v_in", v), lambda: eng.clear_override("v_in"), 10),
            "i_batt": OverrideSlider("Intensité batt.", "A", -30, 80, 10,
                                     lambda v: eng.set_override("i_batt", v), lambda: eng.clear_override("i_batt"), 10),
            "temp_motor": OverrideSlider("Temp. moteur", "°C", 0, 160, 50,
                                         lambda v: eng.set_override("temp_motor", v),
                                         lambda: eng.clear_override("temp_motor"), 10),
            "temp_fet": OverrideSlider("Temp. MOSFET", "°C", 0, 130, 45,
                                       lambda v: eng.set_override("temp_fet", v),
                                       lambda: eng.clear_override("temp_fet"), 10),
        }
        for s in self.sliders.values():
            bl.addWidget(s)
        soc_row = QHBoxLayout()
        soc_row.addWidget(QLabel("Niveau batterie"))
        self.soc = QSlider(Qt.Horizontal); self.soc.setRange(0, 1000); self.soc.setValue(1000)
        self.soc.valueChanged.connect(lambda v: (eng.set_soc(v / 10), self.soc_lbl.setText(f"{v / 10:.1f} %")))
        self.soc_lbl = QLabel("100.0 %"); self.soc_lbl.setMinimumWidth(80)
        soc_row.addWidget(self.soc, 1); soc_row.addWidget(self.soc_lbl)
        bl.addLayout(soc_row)
        thr_row = QHBoxLayout(); thr_row.addWidget(QLabel("Accélérateur (−=frein régén.)"))
        self.thr = QSlider(Qt.Horizontal); self.thr.setRange(-100, 100); self.thr.setValue(0)
        self.thr_lbl = QLabel("0 %"); self.thr_lbl.setMinimumWidth(80)
        self.thr.valueChanged.connect(lambda v: (eng.set_throttle(v / 100), self.thr_lbl.setText(f"{v} %")))
        thr_row.addWidget(self.thr, 1); thr_row.addWidget(self.thr_lbl)
        bl.addLayout(thr_row)
        fl = QHBoxLayout()
        b = QPushButton("Libérer tous les forçages"); b.clicked.connect(self.release_all)
        fl.addWidget(b)
        from PySide6.QtWidgets import QComboBox
        self.fault_cb = QComboBox()
        self.fault_cb.addItem("Défaut : aucun", 0)
        for code in (1, 2, 4, 5, 6, 17, 3):
            self.fault_cb.addItem(f"Défaut {code} — {P.FAULT_NAMES[code]}", code)
        self.fault_cb.currentIndexChanged.connect(lambda _: eng.set_fault(self.fault_cb.currentData()))
        fl.addWidget(self.fault_cb)
        bl.addLayout(fl)
        bl.addStretch()
        mid.addWidget(box, 2)
        root.addLayout(mid, 1)

    def release_all(self):
        for s in self.sliders.values():
            s.release()
        self.thr.setValue(0)
        self.fault_cb.setCurrentIndex(0)

    def on_config(self):
        c = self.ctx.engine.cfg
        self.sliders["v_in"].set_range(c.min_v * 0.8, c.max_v * 1.15, c.nominal_v)
        self.soc.setValue(int(c.soc_pct * 10))

    def refresh(self, t, now: float) -> None:
        for k, _title, _u, fmt in TILES:
            v = getattr(t, k)
            self.tiles[k].set(fmt.format(v), _alert(k, v))
        self.thermal.setText(f"État thermique : {t.thermal_state} — limitation de puissance {t.power_limit_pct:.0f} %"
                             f" — rapport cyclique {t.duty * 100:.0f} % — couple {t.torque_nm:.1f} N·m"
                             f" — ERPM envoyé : {t.erpm:.0f}")
        if t.fault:
            self.fault.setText(f"DÉFAUT CONTRÔLEUR : {P.FAULT_NAMES.get(t.fault, t.fault)} (code {t.fault})")
            self.fault.show()
        else:
            self.fault.hide()
        st = self.ctx.engine.t
        if st == getattr(self, '_last_t', None):
            return
        self._last_t = st
        self.c_rpm.add(st, t.rpm_mech); self.c_spd.add(st, t.speed_kmh); self.c_v.add(st, t.v_in)
        self.c_i.add(st, t.i_batt, t.i_motor); self.c_p.add(st, t.power_w)
        self.c_t.add(st, t.temp_motor, t.temp_fet)
        for c in (self.c_rpm, self.c_spd, self.c_v, self.c_i, self.c_p, self.c_t):
            c.update()

    def clear_charts(self):
        for c in (self.c_rpm, self.c_spd, self.c_v, self.c_i, self.c_p, self.c_t):
            c.clear()
