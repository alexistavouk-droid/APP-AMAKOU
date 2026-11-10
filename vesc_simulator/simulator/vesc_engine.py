"""Moteur de simulation physique simplifié (véhicule + batterie + thermique + défauts)."""
from __future__ import annotations

import math
import threading
import time
from dataclasses import asdict, dataclass, field

from communication import vesc_protocol as P
from simulator.battery_model import BATTERY_PRESETS, BatteryModel
from simulator.telemetry import Telemetry

G = 9.81
RHO = 1.2


@dataclass
class SimConfig:
    name: str = "Trottinette 48 V"
    # batterie
    battery_preset: str = "48V"
    nominal_v: float = 48.0
    max_v: float = 54.6
    min_v: float = 39.0
    capacity_ah: float = 15.0
    soc_pct: float = 100.0
    r_int_mohm: float = 60.0
    # moteur
    pole_count: int = 30                 # nombre de pôles (paires = /2) — ERPM = RPM * paires
    rated_power_w: float = 500.0
    max_power_w: float = 1200.0
    kt_nm_per_a: float = 0.55            # constante de couple (moteur roue)
    phase_resistance_ohm: float = 0.08
    max_motor_current_a: float = 40.0
    max_batt_current_a: float = 25.0
    max_regen_current_a: float = 15.0
    # véhicule
    wheel_diameter_m: float = 0.254
    gear_ratio: float = 1.0
    mass_kg: float = 105.0               # véhicule + pilote
    cda: float = 0.45                    # m² (Cd*A)
    crr: float = 0.012
    # divers
    ambient_c: float = 25.0
    controller_id: int = 0
    fw_major: int = 7
    fw_minor: int = 1
    hw_name: str = "VESC SIMULATOR"

    @property
    def pole_pairs(self) -> int:
        return max(1, self.pole_count // 2)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SimConfig":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def make_battery(self) -> BatteryModel:
        return BatteryModel(self.nominal_v, self.max_v, self.min_v, self.capacity_ah,
                            self.soc_pct / 100.0, self.r_int_mohm / 1000.0)


@dataclass
class LinkFaults:
    """Injection de défauts de communication (utilisé par UART/BLE/CAN)."""
    link_up: bool = True
    drop_rate: float = 0.0       # probabilité de ne pas répondre
    crc_corrupt_rate: float = 0.0
    reply_delay_ms: float = 0.0


OVERRIDE_KEYS = ("rpm", "speed", "v_in", "i_batt", "temp_motor", "temp_fet")


class VescEngine:
    def __init__(self, config: SimConfig | None = None):
        self.lock = threading.RLock()
        self.link = LinkFaults()
        self.scenario = None
        self.running = False
        self.paused = False
        self.time_scale = 1.0
        self.auto_faults = True
        self.configure(config or SimConfig())

    # ------------------------------------------------------------------ état
    def configure(self, cfg: SimConfig) -> None:
        with self.lock:
            self.cfg = cfg
            self.battery = cfg.make_battery()
            self.reset_state()

    def reset_state(self) -> None:
        with self.lock:
            c = self.cfg
            self.t = 0.0
            self.v = 0.0                    # m/s
            self.throttle = 0.0             # -1..1
            self.overrides: dict[str, float] = {}
            self.fault_code = 0
            self._auto_fault = 0
            self.temp_motor = c.ambient_c
            self.temp_fet = c.ambient_c
            self.wh_used = self.wh_regen = self.ah_used = self.ah_regen = 0.0
            self.distance_m = 0.0
            self.odometer_m = 0.0
            self.tach = 0.0
            self.tach_abs = 0.0
            self.link = LinkFaults()
            self.battery = c.make_battery()
            self._prev_v = 0.0
            self.tel = Telemetry(v_nominal=c.nominal_v, controller_id=c.controller_id)
            self.step(0.0, force=True)

    # --------------------------------------------------------------- commandes
    def set_throttle(self, x: float) -> None:
        self.throttle = max(-1.0, min(1.0, x))

    def set_override(self, key: str, value: float) -> None:
        if key not in OVERRIDE_KEYS:
            raise KeyError(key)
        with self.lock:
            self.overrides[key] = float(value)
            if key == "rpm":
                self.overrides.pop("speed", None)
            elif key == "speed":
                self.overrides.pop("rpm", None)

    def clear_override(self, key: str | None = None) -> None:
        with self.lock:
            if key is None:
                self.overrides.clear()
            else:
                self.overrides.pop(key, None)

    def set_soc(self, pct: float) -> None:
        with self.lock:
            self.battery.soc = max(0.0, min(1.0, pct / 100.0))

    def set_speed_state(self, kmh: float) -> None:
        with self.lock:
            self.v = max(0.0, kmh / 3.6)
            self._prev_v = self.v

    def set_fault(self, code: int) -> None:
        self.fault_code = int(code)

    def set_scenario(self, scenario) -> None:
        with self.lock:
            if self.scenario is not None:
                self.scenario.stop(self)
            self.scenario = scenario
            if scenario is not None:
                scenario.begin(self)

    # --------------------------------------------------------------- physique
    def rpm_to_speed(self, rpm_mech: float) -> float:
        c = self.cfg
        return rpm_mech / c.gear_ratio / 60.0 * math.pi * c.wheel_diameter_m

    def _derate(self) -> tuple[float, str]:
        """Limitation de puissance : thermique (MOSFET/moteur) et tension basse."""
        c = self.cfg
        d_f = 1.0 - min(1.0, max(0.0, (self.temp_fet - 80.0) / 20.0))
        d_m = 1.0 - min(1.0, max(0.0, (self.temp_motor - 100.0) / 30.0))
        v = self.battery.terminal_v(0.0)
        d_v = min(1.0, max(0.2, (v - c.min_v) / max(1.0, 0.05 * (c.max_v - c.min_v) + 2.0)))
        d = min(d_f, d_m, d_v)
        state = "NORMAL" if d >= 0.999 else "LIMITATION" if d > 0.3 else "CRITIQUE"
        return d, state

    def step(self, dt: float, force: bool = False) -> Telemetry:
        with self.lock:
            if (self.paused or not self.running) and not force:
                return self.tel
            c, bat, ov = self.cfg, self.battery, self.overrides
            dt_s = dt * self.time_scale
            if dt_s > 0:
                self.t += dt_s
                if self.scenario is not None:
                    self.scenario.update(self, self.t - self.scenario.t0, dt_s)
                    if self.scenario.finished:
                        self.scenario.stop(self)
                        self.scenario = None

            derate, tstate = self._derate()
            faulted = (self.fault_code or self._auto_fault) != 0
            thr = 0.0 if faulted else self.throttle

            # --- vitesse imposée ?
            v_forced = None
            if "rpm" in ov:
                v_forced = self.rpm_to_speed(ov["rpm"])
            elif "speed" in ov:
                v_forced = ov["speed"] / 3.6
            r = c.wheel_diameter_m / 2.0
            kt_wheel = c.kt_nm_per_a * c.gear_ratio / r      # N par A de courant moteur

            f_roll = c.crr * c.mass_kg * G if self.v > 0.05 else 0.0
            f_drag = 0.5 * RHO * c.cda * self.v ** 2

            # courant moteur demandé (limité par thermique, rapport cyclique, puissance)
            if thr >= 0:
                iq = thr * c.max_motor_current_a * derate
            else:
                iq = thr * c.max_regen_current_a * (1.0 if self.v > 0.5 else 0.0)
            omega = self.v / r * c.gear_ratio
            duty = min(1.0, omega * c.kt_nm_per_a * 0.9 / max(bat.terminal_v(0.0), 1.0))
            if iq > 0:
                iq *= min(1.0, max(0.0, (0.95 - duty) / 0.10))
            vb = max(bat.terminal_v(0.0), 1.0)
            p_mech = iq * kt_wheel * self.v
            p_elec = p_mech + 1.5 * c.phase_resistance_ohm * iq ** 2 + 5.0
            if p_elec > 0:
                lim = min(c.max_power_w * derate, c.max_batt_current_a * vb)
                if p_elec > lim:
                    iq *= max(0.0, lim / p_elec)

            if v_forced is not None:
                a = (v_forced - self._prev_v) / dt_s if dt_s > 1e-9 else 0.0
                f_need = f_roll + f_drag + c.mass_kg * a
                self.v = max(0.0, v_forced)
                iq = max(-c.max_regen_current_a, min(c.max_motor_current_a, f_need / kt_wheel))
            else:
                f_drive = iq * kt_wheel
                f_brake = 0.0
                a = (f_drive - f_roll - f_drag - f_brake) / c.mass_kg
                if dt_s > 0:
                    self.v = max(0.0, self.v + a * dt_s)
                    if self.v < 0.02 and f_drive <= f_roll:
                        self.v = 0.0
            self._prev_v = self.v

            # --- électrique
            rpm_mech = self.v / (math.pi * c.wheel_diameter_m) * 60.0 * c.gear_ratio
            p_mech = iq * kt_wheel * self.v
            p_loss = 1.5 * c.phase_resistance_ohm * iq ** 2
            p_elec = p_mech + p_loss + (0.0 if faulted and iq == 0 else 5.0)
            v_term = bat.terminal_v(0.0)
            i_batt = p_elec / max(v_term, 1.0)
            v_term = bat.terminal_v(i_batt)
            i_batt = p_elec / max(v_term, 1.0)
            v_term = bat.terminal_v(i_batt)
            omega = self.v / r * c.gear_ratio
            duty = min(1.0, omega * c.kt_nm_per_a * 0.9 / max(v_term, 1.0))

            if "i_batt" in ov:
                i_batt = ov["i_batt"]
                iq = max(-c.max_regen_current_a * 2, min(c.max_motor_current_a * 2,
                                                          i_batt / max(duty, 0.1)))
                v_term = bat.terminal_v(i_batt)
            v_meas = ov.get("v_in", v_term)
            p_batt = i_batt * v_meas

            # --- énergie
            if dt_s > 0:
                bat.integrate(i_batt, dt_s)
                e = abs(p_batt) * dt_s / 3600.0
                q = abs(i_batt) * dt_s / 3600.0
                if i_batt >= 0:
                    self.wh_used += e
                    self.ah_used += q
                else:
                    self.wh_regen += e
                    self.ah_regen += q
                self.distance_m += self.v * dt_s
                self.odometer_m += self.v * dt_s
                d_tach = rpm_mech * c.pole_pairs / 60.0 * 6.0 * dt_s
                self.tach += d_tach
                self.tach_abs += abs(d_tach)

                # thermique (1er ordre)
                air = 1.0 + 0.08 * (self.v * 3.6)
                p_fet = 0.015 * iq ** 2 + 0.02 * abs(iq) * duty * 10 + 1.0
                tm_inf = c.ambient_c + p_loss * 1.6 / air
                tf_inf = c.ambient_c + p_fet * 1.2 / (1 + 0.02 * air)
                self.temp_motor += (tm_inf - self.temp_motor) * min(1.0, dt_s / 60.0)
                self.temp_fet += (tf_inf - self.temp_fet) * min(1.0, dt_s / 30.0)
            if "temp_motor" in ov:
                self.temp_motor = ov["temp_motor"]
            if "temp_fet" in ov:
                self.temp_fet = ov["temp_fet"]

            # --- défauts automatiques
            if self.auto_faults:
                auto = 0
                if v_meas > c.max_v * 1.08:
                    auto = P.FAULT_OVER_VOLTAGE
                elif v_meas < c.min_v * 0.92:
                    auto = P.FAULT_UNDER_VOLTAGE
                elif self.temp_fet > 105:
                    auto = P.FAULT_OVER_TEMP_FET
                elif self.temp_motor > 140:
                    auto = P.FAULT_OVER_TEMP_MOTOR
                self._auto_fault = auto

            # --- instantané
            dist_km = self.distance_m / 1000.0
            speed_kmh = self.v * 3.6
            wh_net = self.wh_used - self.wh_regen
            if dist_km > 0.05:
                whkm = wh_net / dist_km
            elif speed_kmh > 1.0:
                whkm = max(0.0, p_batt) / speed_kmh
            else:
                whkm = 0.0
            t = self.tel
            t.rpm_mech = rpm_mech
            t.erpm = rpm_mech * c.pole_pairs
            t.speed_kmh = speed_kmh
            t.torque_nm = iq * c.kt_nm_per_a
            t.i_motor = iq
            t.duty = duty
            t.v_in = v_meas
            t.v_nominal = c.nominal_v
            t.i_batt = i_batt
            t.power_w = p_batt
            t.soc_pct = bat.soc * 100.0
            t.wh_used, t.wh_regen = self.wh_used, self.wh_regen
            t.ah_used, t.ah_regen = self.ah_used, self.ah_regen
            t.wh_per_km = whkm
            t.wh_left = bat.wh_left
            t.temp_fet, t.temp_motor = self.temp_fet, self.temp_motor
            t.power_limit_pct = derate * 100.0
            t.thermal_state = tstate
            t.fault = self.fault_code or self._auto_fault
            t.distance_km = dist_km
            t.odometer_m = self.odometer_m
            t.tachometer = int(self.tach)
            t.tachometer_abs = int(self.tach_abs)
            t.uptime_ms = int(self.t * 1000)
            return t

    def snapshot(self) -> Telemetry:
        with self.lock:
            return self.tel.copy()

    # ------------------------------------------------------------- thread temps réel
    def start(self) -> None:
        with self.lock:
            self.running, self.paused = True, False
        if getattr(self, "_thread", None) is None or not self._thread.is_alive():
            self._stop_evt = threading.Event()
            self._thread = threading.Thread(target=self._loop, name="vesc-sim", daemon=True)
            self._thread.start()

    def pause(self, on: bool = True) -> None:
        self.paused = on

    def stop(self) -> None:
        self.running = False
        self.throttle = 0.0

    def shutdown(self) -> None:
        self.running = False
        if getattr(self, "_thread", None) is not None:
            self._stop_evt.set()
            self._thread.join(1.0)

    def _loop(self, rate_hz: float = 50.0) -> None:
        dt = 1.0 / rate_hz
        last = time.perf_counter()
        while not self._stop_evt.is_set():
            time.sleep(dt)
            now = time.perf_counter()
            self.step(min(now - last, 0.2))
            last = now
