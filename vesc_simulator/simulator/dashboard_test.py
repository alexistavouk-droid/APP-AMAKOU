"""Mode DASHBOARD TEST : vérifie ce que l'ESP32 demande / reçoit et aide à comparer avec l'écran."""
from __future__ import annotations

import time
from dataclasses import dataclass

from communication import vesc_protocol as P

CONNECT_TIMEOUT_S = 3.0


@dataclass
class CheckResult:
    name: str
    status: str      # OK / ATTENTE / ÉCHEC / MANUEL
    detail: str = ""


# Vecteur de référence : valeurs rondes faciles à relire sur l'écran du tableau de bord.
REFERENCE_VECTOR = {
    "rpm_mech": 500.0,       # tr/min mécanique
    "v_in": 48.0, "i_batt": 10.0, "temp_motor": 55.0, "temp_fet": 40.0, "soc": 50.0,
}


class DashboardTester:
    def __init__(self, engine, log, clock=time.time):
        self.engine, self.log, self.clock = engine, log, clock
        self.link_phase = "idle"       # idle / cut / restored / done
        self._t_cut = self._t_restore = 0.0
        self.cut_duration = 6.0
        self.return_delay_s: float | None = None
        self.outage_requests = 0

    # --------------------------------------------------------------- valeurs de référence
    def apply_reference_vector(self) -> None:
        e = self.engine
        e.set_throttle(0.0)
        e.set_override("rpm", REFERENCE_VECTOR["rpm_mech"])
        e.set_override("v_in", REFERENCE_VECTOR["v_in"])
        e.set_override("i_batt", REFERENCE_VECTOR["i_batt"])
        e.set_override("temp_motor", REFERENCE_VECTOR["temp_motor"])
        e.set_override("temp_fet", REFERENCE_VECTOR["temp_fet"])
        e.set_soc(REFERENCE_VECTOR["soc"])
        e.set_fault(0)

    def release(self) -> None:
        self.engine.clear_override()

    def sent_table(self) -> list[tuple[str, str, str]]:
        """(paramètre, valeur côté simulateur, valeur codée dans la trame VESC)."""
        t = self.engine.snapshot()
        v = t.vesc_values()
        s = t.vesc_setup_values()
        return [
            ("RPM (électrique, GET_VALUES)", f"{t.erpm:.0f}", f"{int(v['rpm'])}"),
            ("RPM mécanique", f"{t.rpm_mech:.0f}", "—"),
            ("Vitesse (m/s, SETUP)", f"{t.speed_kmh:.1f} km/h", f"{int(s['speed'] * 1000)} (×1e3 m/s)"),
            ("Tension batterie", f"{t.v_in:.1f} V", f"{int(v['v_in'] * 10)} (×10)"),
            ("Courant batterie", f"{t.i_batt:.2f} A", f"{int(v['avg_input_current'] * 100)} (×100)"),
            ("Courant moteur", f"{t.i_motor:.2f} A", f"{int(v['avg_motor_current'] * 100)} (×100)"),
            ("Température MOSFET", f"{t.temp_fet:.1f} °C", f"{int(v['temp_fet'] * 10)} (×10)"),
            ("Température moteur", f"{t.temp_motor:.1f} °C", f"{int(v['temp_motor'] * 10)} (×10)"),
            ("Niveau batterie (SETUP)", f"{t.soc_pct:.1f} %", f"{int(s['battery_level'] * 1000)} (×1000)"),
            ("Défaut", f"{t.fault} ({P.FAULT_NAMES.get(t.fault, '?')})", f"{t.fault}"),
        ]

    # --------------------------------------------------------------- test de liaison
    def start_link_test(self, cut_s: float = 6.0) -> None:
        self.cut_duration = cut_s
        self.link_phase = "cut"
        self._t_cut = self.clock()
        self.return_delay_s = None
        self.outage_requests = self.log.count("rx_frames")
        self.engine.link.link_up = False

    def tick(self) -> None:
        now = self.clock()
        if self.link_phase == "cut" and now - self._t_cut >= self.cut_duration:
            self.engine.link.link_up = True
            self._t_restore = now
            self.outage_requests = self.log.count("rx_frames") - self.outage_requests
            self.link_phase = "restored"
            self._tx_at_restore = self.log.count("tx_frames")
        elif self.link_phase == "restored" and self.log.count("tx_frames") > self._tx_at_restore:
            self.return_delay_s = now - self._t_restore
            self.link_phase = "done"

    # --------------------------------------------------------------- vérifications
    def checks(self) -> list[CheckResult]:
        lg = self.log
        r: list[CheckResult] = []
        since = lg.seconds_since()
        if since is None:
            r.append(CheckResult("Connexion", "ATTENTE", "Aucune requête reçue de l'ESP32."))
        elif since <= CONNECT_TIMEOUT_S:
            r.append(CheckResult("Connexion", "OK", f"Dernière requête il y a {since:.1f} s."))
        else:
            r.append(CheckResult("Connexion", "ÉCHEC", f"Plus de requête depuis {since:.1f} s."))

        def seen(cmds, label, what):
            n = sum(lg.cmd_count.get(c, 0) for c in cmds)
            if n == 0:
                r.append(CheckResult(label, "ATTENTE", f"{what} : jamais demandé "
                                                     f"({'/'.join(P.comm_name(c) for c in cmds)})."))
            else:
                hz = max(lg.rate_hz(c) for c in cmds)
                r.append(CheckResult(label, "OK", f"{n} requêtes, ~{hz:.1f} Hz — {what} envoyé(e)."))

        gv = [P.COMM_GET_VALUES, P.COMM_GET_VALUES_SELECTIVE]
        gs = [P.COMM_GET_VALUES_SETUP, P.COMM_GET_VALUES_SETUP_SELECTIVE]
        seen(gv + gs, "Réception des RPM", "RPM (ERPM)")
        seen(gv + gs, "Tension batterie", "tension")
        seen(gv + gs, "Courant", "courants moteur/batterie")
        seen(gv + gs, "Températures", "températures MOSFET/moteur")
        seen(gs, "État de la batterie", "niveau batterie (battery_level)")
        seen(gv + gs, "Défauts", "code défaut")
        if lg.count("crc_errors"):
            r.append(CheckResult("Intégrité des trames", "ÉCHEC", f"{lg.count('crc_errors')} erreur(s) CRC reçues."))
        else:
            r.append(CheckResult("Intégrité des trames", "OK", "Aucune erreur CRC."))
        warn = lg.check_refresh(P.COMM_GET_VALUES) or lg.check_refresh(P.COMM_GET_VALUES_SETUP)
        if warn:
            r.append(CheckResult("Rafraîchissement", "ÉCHEC", warn))
        # déconnexion / retour
        if self.link_phase == "idle":
            r.append(CheckResult("Déconnexion", "MANUEL", "Lancer « Test déconnexion » puis observer l'écran."))
            r.append(CheckResult("Retour de connexion", "MANUEL", "—"))
        elif self.link_phase == "cut":
            r.append(CheckResult("Déconnexion", "MANUEL", "Liaison coupée : l'écran doit afficher « déconnecté »."))
            r.append(CheckResult("Retour de connexion", "ATTENTE", "—"))
        else:
            r.append(CheckResult("Déconnexion", "OK" if self.outage_requests >= 0 else "ATTENTE",
                                 f"{self.outage_requests} requête(s) ESP32 restées sans réponse."))
            if self.link_phase == "done":
                r.append(CheckResult("Retour de connexion", "OK",
                                     f"Réponse reprise {self.return_delay_s:.2f} s après rétablissement."))
            else:
                r.append(CheckResult("Retour de connexion", "ATTENTE", "En attente d'une requête de l'ESP32…"))
        return r
