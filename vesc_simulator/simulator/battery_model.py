"""Modèle de batterie Li-ion : courbe de tension à vide (OCV) + résistance interne.

Tension nominale (étiquette du pack) != tension mesurée : mesurée = OCV(SoC) - I * R_int.
"""
from __future__ import annotations

from dataclasses import dataclass

# (SoC 0..1, fraction de la plage [Vmin..Vmax]) — courbe Li-ion typique
_OCV_CURVE = [(0.0, 0.0), (0.05, 0.12), (0.10, 0.22), (0.20, 0.38), (0.30, 0.48),
              (0.50, 0.62), (0.70, 0.76), (0.90, 0.92), (1.0, 1.0)]

# nom -> (cellules en série, V nominale, V max, V min)
BATTERY_PRESETS = {
    "36V": (10, 36.0, 42.0, 30.0),
    "48V": (13, 48.0, 54.6, 39.0),
    "52V": (14, 52.0, 58.8, 42.0),
    "60V": (16, 60.0, 67.2, 48.0),
    "72V": (20, 72.0, 84.0, 60.0),
    "84V": (24, 84.0, 100.8, 72.0),
}


def ocv_fraction(soc: float) -> float:
    soc = min(1.0, max(0.0, soc))
    for (x0, y0), (x1, y1) in zip(_OCV_CURVE, _OCV_CURVE[1:]):
        if soc <= x1:
            return y0 + (y1 - y0) * (soc - x0) / (x1 - x0)
    return 1.0


@dataclass
class BatteryModel:
    nominal_v: float = 48.0
    max_v: float = 54.6
    min_v: float = 39.0
    capacity_ah: float = 15.0
    soc: float = 1.0              # 0..1
    r_int_ohm: float = 0.060

    @property
    def capacity_wh(self) -> float:
        return self.capacity_ah * self.nominal_v

    def open_circuit_v(self, soc: float | None = None) -> float:
        s = self.soc if soc is None else soc
        return self.min_v + (self.max_v - self.min_v) * ocv_fraction(s)

    def terminal_v(self, current_a: float) -> float:
        """Tension aux bornes (courant > 0 = décharge → chute de tension)."""
        return max(0.0, self.open_circuit_v() - current_a * self.r_int_ohm)

    def integrate(self, current_a: float, dt: float) -> None:
        self.soc = min(1.0, max(0.0, self.soc - current_a * dt / 3600.0 / self.capacity_ah))

    @property
    def wh_left(self) -> float:
        return self.soc * self.capacity_wh

    @classmethod
    def preset(cls, name: str, capacity_ah: float = 15.0) -> "BatteryModel":
        _, nom, vmax, vmin = BATTERY_PRESETS[name]
        return cls(nominal_v=nom, max_v=vmax, min_v=vmin, capacity_ah=capacity_ah)
