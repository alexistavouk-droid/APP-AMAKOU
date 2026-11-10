"""Structure de télémétrie + conversion vers les champs du protocole VESC."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields


@dataclass
class Telemetry:
    # --- moteur
    rpm_mech: float = 0.0        # tr/min mécaniques (roue/moteur)
    erpm: float = 0.0            # RPM électrique = rpm_mech * paires de pôles (valeur envoyée au VESC)
    speed_kmh: float = 0.0
    torque_nm: float = 0.0
    i_motor: float = 0.0         # A (>0 traction, <0 régénération)
    i_d: float = 0.0
    duty: float = 0.0
    # --- batterie
    v_in: float = 0.0            # tension mesurée
    v_nominal: float = 0.0
    i_batt: float = 0.0          # A (>0 décharge, <0 recharge)
    power_w: float = 0.0
    soc_pct: float = 100.0
    wh_used: float = 0.0
    wh_regen: float = 0.0
    ah_used: float = 0.0
    ah_regen: float = 0.0
    wh_per_km: float = 0.0
    wh_left: float = 0.0
    # --- contrôleur
    temp_fet: float = 25.0
    temp_motor: float = 25.0
    power_limit_pct: float = 100.0
    thermal_state: str = "NORMAL"   # NORMAL / LIMITATION / CRITIQUE
    fault: int = 0
    # --- trajet
    distance_km: float = 0.0
    odometer_m: float = 0.0
    tachometer: int = 0
    tachometer_abs: int = 0
    uptime_ms: int = 0
    controller_id: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    def copy(self) -> "Telemetry":
        return Telemetry(**{f.name: getattr(self, f.name) for f in fields(self)})

    # -- valeurs au format des réponses VESC (unités du firmware) ---------------
    def vesc_values(self) -> dict:
        return {
            "temp_fet": self.temp_fet, "temp_motor": self.temp_motor,
            "avg_motor_current": self.i_motor, "avg_input_current": self.i_batt,
            "avg_id": self.i_d, "avg_iq": self.i_motor,
            "duty": self.duty, "rpm": self.erpm, "v_in": self.v_in,
            "amp_hours": self.ah_used, "amp_hours_charged": self.ah_regen,
            "watt_hours": self.wh_used, "watt_hours_charged": self.wh_regen,
            "tachometer": self.tachometer, "tachometer_abs": self.tachometer_abs,
            "fault": self.fault, "pid_pos": 0.0, "controller_id": self.controller_id,
            "temp_mos1": self.temp_fet, "temp_mos2": self.temp_fet, "temp_mos3": self.temp_fet,
            "avg_vd": 0.0, "avg_vq": self.duty * self.v_in * 0.577, "status": 0,
        }

    def vesc_setup_values(self) -> dict:
        return {
            "temp_fet": self.temp_fet, "temp_motor": self.temp_motor,
            "current_tot": self.i_motor, "current_in_tot": self.i_batt,
            "duty": self.duty, "rpm": self.erpm,
            "speed": self.speed_kmh / 3.6,            # m/s (signé) dans le protocole
            "v_in": self.v_in, "battery_level": self.soc_pct / 100.0,
            "amp_hours": self.ah_used, "amp_hours_charged": self.ah_regen,
            "watt_hours": self.wh_used, "watt_hours_charged": self.wh_regen,
            "distance": self.distance_km * 1000.0, "distance_abs": self.distance_km * 1000.0,
            "pid_pos": 0.0, "fault": self.fault, "controller_id": self.controller_id,
            "num_vescs": 1, "wh_batt_left": self.wh_left,
            "odometer": int(self.odometer_m), "uptime_ms": self.uptime_ms,
        }
