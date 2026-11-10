"""Scénarios de test prédéfinis. Un scénario pilote le moteur via accélérateur, forçages et défauts."""
from __future__ import annotations

from communication import vesc_protocol as P


def _lerp(a: float, b: float, x: float) -> float:
    return a + (b - a) * max(0.0, min(1.0, x))


class Scenario:
    id = 0
    name = ""
    description = ""
    duration = 20.0

    def __init__(self):
        self.t0 = 0.0
        self.finished = False

    def begin(self, eng) -> None:
        self.t0 = eng.t
        self.finished = False
        self.on_begin(eng)

    def on_begin(self, eng) -> None: ...

    def update(self, eng, t: float, dt: float) -> None:
        self.on_update(eng, t, dt)
        if t >= self.duration:
            self.finished = True

    def on_update(self, eng, t: float, dt: float) -> None: ...

    def stop(self, eng) -> None:
        self.on_stop(eng)

    def on_stop(self, eng) -> None: ...


class Startup(Scenario):
    id, name, duration = 1, "Démarrage", 10.0
    description = "Batterie chargée, moteur à l'arrêt, températures normales."

    def on_begin(self, eng):
        eng.reset_state()
        eng.running = True
        eng.set_soc(100)
        self.t0 = eng.t


class Acceleration(Scenario):
    id, name, duration = 2, "Accélération", 25.0
    description = "Accélération progressive : RPM, vitesse, courant et puissance augmentent."

    def on_update(self, eng, t, dt):
        eng.set_throttle(_lerp(0.0, 0.8, t / 12.0))

    def on_stop(self, eng):
        eng.set_throttle(0.3)


class Deceleration(Scenario):
    id, name, duration = 3, "Décélération", 20.0
    description = "Départ à 40 km/h, lâcher d'accélérateur puis freinage doux."

    def on_begin(self, eng):
        eng.set_speed_state(40.0)

    def on_update(self, eng, t, dt):
        eng.set_throttle(0.0 if t < 5 else -0.15)


class LowBattery(Scenario):
    id, name, duration = 4, "Batterie faible", 60.0
    description = "SoC 12 % → 10 % → 5 % → 3 % avec chute progressive de la tension."

    def on_begin(self, eng):
        eng.set_soc(12)

    def on_update(self, eng, t, dt):
        eng.set_throttle(0.25)
        eng.set_soc(_lerp(12.0, 3.0, t / 55.0))


class Overheat(Scenario):
    id, name, duration = 5, "Surchauffe", 60.0
    description = "Montée progressive des températures moteur (jusqu'à 140 °C) et MOSFET (jusqu'à 108 °C)."

    def on_begin(self, eng):
        eng.set_throttle(0.5)

    def on_update(self, eng, t, dt):
        eng.set_override("temp_motor", _lerp(40, 140, t / 50.0))
        eng.set_override("temp_fet", _lerp(45, 108, t / 50.0))

    def on_stop(self, eng):
        eng.clear_override("temp_motor")
        eng.clear_override("temp_fet")
        eng.set_throttle(0.0)


class HardAcceleration(Scenario):
    id, name, duration = 6, "Forte accélération", 20.0
    description = "Plein gaz : demande de puissance et courant maximaux."

    def on_update(self, eng, t, dt):
        eng.set_throttle(1.0 if t < 14 else 0.0)

    def on_stop(self, eng):
        eng.set_throttle(0.0)


class Regen(Scenario):
    id, name, duration = 7, "Freinage régénératif", 25.0
    description = "Départ à 35 km/h puis freinage régénératif : courant batterie négatif (recharge)."

    def on_begin(self, eng):
        eng.set_speed_state(35.0)

    def on_update(self, eng, t, dt):
        eng.set_throttle(0.2 if t < 3 else -0.7)


class Faults(Scenario):
    id, name, duration = 8, "Défauts contrôleur", 42.0
    description = ("Surtension, sous-tension, surchauffe, surintensité, défaut de communication, "
                   "erreur moteur (6 s chacun).")
    STEPS = [
        ("Surtension", P.FAULT_OVER_VOLTAGE),
        ("Sous-tension", P.FAULT_UNDER_VOLTAGE),
        ("Surchauffe MOSFET", P.FAULT_OVER_TEMP_FET),
        ("Surintensité", P.FAULT_ABS_OVER_CURRENT),
        ("Défaut de communication", None),
        ("Erreur moteur", P.FAULT_UNBALANCED_CURRENTS),
    ]

    def __init__(self):
        super().__init__()
        self.current = "-"

    def on_begin(self, eng):
        eng.set_throttle(0.3)
        self._idx = -1

    def _clear(self, eng):
        eng.set_fault(0)
        eng.clear_override("v_in")
        eng.clear_override("temp_fet")
        eng.clear_override("i_batt")
        eng.link.drop_rate = 0.0
        eng.link.crc_corrupt_rate = 0.0

    def on_update(self, eng, t, dt):
        idx = int(t // 6)
        if idx >= len(self.STEPS):
            self._clear(eng)
            return
        if idx != self._idx:
            self._clear(eng)
            self._idx = idx
            self.current, code = self.STEPS[idx]
            c = eng.cfg
            if code == P.FAULT_OVER_VOLTAGE:
                eng.set_override("v_in", c.max_v * 1.12)
            elif code == P.FAULT_UNDER_VOLTAGE:
                eng.set_override("v_in", c.min_v * 0.85)
            elif code == P.FAULT_OVER_TEMP_FET:
                eng.set_override("temp_fet", 112.0)
            elif code == P.FAULT_ABS_OVER_CURRENT:
                eng.set_override("i_batt", c.max_batt_current_a * 3.0)
            elif code is None:                       # défaut de communication
                eng.link.drop_rate = 0.5
                eng.link.crc_corrupt_rate = 0.3
            if code:
                eng.set_fault(code)

    def on_stop(self, eng):
        self._clear(eng)
        eng.set_throttle(0.0)


class LinkLoss(Scenario):
    id, name, duration = 9, "Perte de connexion", 20.0
    description = "Coupe les réponses 8 s (t=4 s) puis rétablit la liaison : le tableau de bord doit détecter les deux."

    def on_begin(self, eng):
        eng.set_throttle(0.3)

    def on_update(self, eng, t, dt):
        eng.link.link_up = not (4.0 <= t < 12.0)

    def on_stop(self, eng):
        eng.link.link_up = True
        eng.set_throttle(0.0)


SCENARIOS = [Startup, Acceleration, Deceleration, LowBattery, Overheat, HardAcceleration,
             Regen, Faults, LinkLoss]


def make_scenario(sid: int) -> Scenario:
    for cls in SCENARIOS:
        if cls.id == sid:
            return cls()
    raise KeyError(sid)
