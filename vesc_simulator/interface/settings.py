"""Onglet réglages : batterie, moteur, contrôleur, véhicule + profils JSON."""
from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from simulator.battery_model import BATTERY_PRESETS
from simulator.profiles import list_profiles, load_profile, save_profile
from simulator.vesc_engine import SimConfig


def dspin(lo, hi, step=1.0, dec=1, suffix=""):
    s = QDoubleSpinBox(); s.setRange(lo, hi); s.setSingleStep(step); s.setDecimals(dec)
    if suffix:
        s.setSuffix(" " + suffix)
    return s


class SettingsTab(QWidget):
    def __init__(self, ctx, on_applied):
        super().__init__()
        self.ctx, self.on_applied = ctx, on_applied
        root = QVBoxLayout(self)

        prof = QGroupBox("Profils de simulation (JSON)")
        pl = QHBoxLayout(prof)
        self.prof_cb = QComboBox(); self.prof_cb.setMinimumWidth(220)
        b_load = QPushButton("Charger"); b_load.clicked.connect(self.load)
        self.save_name = QLineEdit(); self.save_name.setPlaceholderText("nom du profil à enregistrer")
        b_save = QPushButton("Enregistrer"); b_save.clicked.connect(self.save)
        for w in (QLabel("Profil :"), self.prof_cb, b_load, self.save_name, b_save):
            pl.addWidget(w)
        root.addWidget(prof)
        self.refresh_profiles()

        cols = QHBoxLayout()
        # --- batterie
        gb = QGroupBox("Batterie"); f = QFormLayout(gb)
        self.preset = QComboBox(); self.preset.addItems(list(BATTERY_PRESETS) + ["Personnalisée"])
        self.preset.currentTextChanged.connect(self._preset)
        self.nom = dspin(10, 200, 0.5, 1, "V"); self.vmax = dspin(10, 200, 0.5, 1, "V")
        self.vmin = dspin(5, 200, 0.5, 1, "V"); self.ah = dspin(1, 500, 0.5, 1, "Ah")
        self.wh = QLabel("—"); self.soc = dspin(0, 100, 1, 1, "%"); self.rint = dspin(1, 500, 1, 0, "mΩ")
        for lab, w in [("Profil", self.preset), ("Tension nominale (étiquette)", self.nom),
                       ("Tension maximale", self.vmax), ("Tension minimale", self.vmin),
                       ("Capacité", self.ah), ("Capacité énergétique", self.wh),
                       ("Charge initiale", self.soc), ("Résistance interne", self.rint)]:
            f.addRow(lab, w)
        for w in (self.nom, self.ah):
            w.valueChanged.connect(self._wh)
        cols.addWidget(gb)
        # --- moteur
        gm = QGroupBox("Moteur"); f = QFormLayout(gm)
        self.poles = QSpinBox(); self.poles.setRange(2, 100); self.poles.setSingleStep(2)
        self.prated = dspin(50, 20000, 50, 0, "W"); self.pmax = dspin(50, 40000, 50, 0, "W")
        self.kt = dspin(0.02, 5, 0.01, 2, "N·m/A"); self.rph = dspin(0.001, 2, 0.005, 3, "Ω")
        for lab, w in [("Nombre de pôles", self.poles), ("Puissance nominale", self.prated),
                       ("Puissance maximale", self.pmax), ("Constante de couple", self.kt),
                       ("Résistance de phase", self.rph)]:
            f.addRow(lab, w)
        cols.addWidget(gm)
        # --- contrôleur
        gc = QGroupBox("Contrôleur"); f = QFormLayout(gc)
        self.imot = dspin(5, 500, 1, 0, "A"); self.ibat = dspin(5, 300, 1, 0, "A"); self.ireg = dspin(0, 200, 1, 0, "A")
        self.cid = QSpinBox(); self.cid.setRange(0, 254)
        self.fwM = QSpinBox(); self.fwM.setRange(0, 99); self.fwm = QSpinBox(); self.fwm.setRange(0, 99)
        self.hw = QLineEdit()
        for lab, w in [("Courant moteur max", self.imot), ("Courant batterie max", self.ibat),
                       ("Courant régén. max", self.ireg), ("ID contrôleur / CAN", self.cid),
                       ("Firmware (majeur)", self.fwM), ("Firmware (mineur)", self.fwm), ("Nom matériel", self.hw)]:
            f.addRow(lab, w)
        cols.addWidget(gc)
        # --- véhicule
        gv = QGroupBox("Véhicule"); f = QFormLayout(gv)
        self.wheel = dspin(0.1, 1.0, 0.01, 3, "m"); self.gear = dspin(0.2, 20, 0.1, 2)
        self.mass = dspin(10, 1000, 5, 0, "kg"); self.amb = dspin(-30, 50, 1, 0, "°C")
        for lab, w in [("Diamètre de roue", self.wheel), ("Rapport de réduction", self.gear),
                       ("Masse totale", self.mass), ("Température ambiante", self.amb)]:
            f.addRow(lab, w)
        cols.addWidget(gv)
        root.addLayout(cols)
        ap = QPushButton("Appliquer la configuration"); ap.setObjectName("primary"); ap.clicked.connect(self.apply)
        root.addWidget(ap)
        self.msg = QLabel(""); root.addWidget(self.msg); root.addStretch()
        self.fill(ctx.engine.cfg)

    def refresh_profiles(self):
        cur = self.prof_cb.currentText()
        self.prof_cb.clear(); self.prof_cb.addItems(list_profiles())
        i = self.prof_cb.findText(cur)
        if i >= 0:
            self.prof_cb.setCurrentIndex(i)

    def _wh(self, *_):
        self.wh.setText(f"{self.nom.value() * self.ah.value():.0f} Wh")

    def _preset(self, name):
        if name in BATTERY_PRESETS:
            _, nom, vmax, vmin = BATTERY_PRESETS[name]
            self.nom.setValue(nom); self.vmax.setValue(vmax); self.vmin.setValue(vmin)

    def fill(self, c: SimConfig):
        self.preset.blockSignals(True)
        self.preset.setCurrentText(c.battery_preset if c.battery_preset in BATTERY_PRESETS else "Personnalisée")
        self.preset.blockSignals(False)
        self.nom.setValue(c.nominal_v); self.vmax.setValue(c.max_v); self.vmin.setValue(c.min_v)
        self.ah.setValue(c.capacity_ah); self.soc.setValue(c.soc_pct); self.rint.setValue(c.r_int_mohm)
        self.poles.setValue(c.pole_count); self.prated.setValue(c.rated_power_w); self.pmax.setValue(c.max_power_w)
        self.kt.setValue(c.kt_nm_per_a); self.rph.setValue(c.phase_resistance_ohm)
        self.imot.setValue(c.max_motor_current_a); self.ibat.setValue(c.max_batt_current_a)
        self.ireg.setValue(c.max_regen_current_a); self.cid.setValue(c.controller_id)
        self.fwM.setValue(c.fw_major); self.fwm.setValue(c.fw_minor); self.hw.setText(c.hw_name)
        self.wheel.setValue(c.wheel_diameter_m); self.gear.setValue(c.gear_ratio); self.mass.setValue(c.mass_kg)
        self.amb.setValue(c.ambient_c); self._wh()
        self._name = c.name

    def collect(self) -> SimConfig:
        p = self.preset.currentText()
        return SimConfig(
            name=getattr(self, "_name", "Personnalisée"), battery_preset=p, nominal_v=self.nom.value(),
            max_v=self.vmax.value(), min_v=self.vmin.value(), capacity_ah=self.ah.value(),
            soc_pct=self.soc.value(), r_int_mohm=self.rint.value(), pole_count=self.poles.value(),
            rated_power_w=self.prated.value(), max_power_w=self.pmax.value(), kt_nm_per_a=self.kt.value(),
            phase_resistance_ohm=self.rph.value(), max_motor_current_a=self.imot.value(),
            max_batt_current_a=self.ibat.value(), max_regen_current_a=self.ireg.value(),
            wheel_diameter_m=self.wheel.value(), gear_ratio=self.gear.value(), mass_kg=self.mass.value(),
            ambient_c=self.amb.value(), controller_id=self.cid.value(), fw_major=self.fwM.value(),
            fw_minor=self.fwm.value(), hw_name=self.hw.text() or "VESC SIMULATOR")

    def apply(self):
        cfg = self.collect()
        if not (cfg.min_v < cfg.nominal_v < cfg.max_v):
            QMessageBox.warning(self, "Batterie", "Il faut : Vmin < Vnominale < Vmax.")
            return
        self.ctx.engine.configure(cfg)
        self.msg.setText(f"Configuration appliquée : {cfg.name} — {cfg.nominal_v:.0f} V nominal, "
                         f"{cfg.max_v:.1f} V max, {cfg.pole_count // 2} paires de pôles.")
        self.on_applied()

    def load(self):
        name = self.prof_cb.currentText()
        if name:
            cfg = load_profile(name)
            self.fill(cfg)
            self.apply()

    def save(self):
        name = self.save_name.text().strip().replace(" ", "_") or self.prof_cb.currentText()
        if not name:
            return
        cfg = self.collect()
        cfg.name = self.save_name.text().strip() or cfg.name
        save_profile(cfg, name)
        self.refresh_profiles()
        self.prof_cb.setCurrentText(name)
        self.msg.setText(f"Profil enregistré : profiles/{name}.json")
