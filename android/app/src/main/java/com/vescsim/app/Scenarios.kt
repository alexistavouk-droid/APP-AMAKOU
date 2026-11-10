package com.vescsim.app

abstract class Scenario(val id: Int, val name: String, val description: String, val duration: Double) {
    var t0 = 0.0
    var finished = false
    var current = ""
    fun begin(e: Engine) { t0 = e.t; finished = false; onBegin(e) }
    fun update(e: Engine, t: Double, dt: Double) { onUpdate(e, t, dt); if (t >= duration) finished = true }
    fun stop(e: Engine) = onStop(e)
    open fun onBegin(e: Engine) {}
    open fun onUpdate(e: Engine, t: Double, dt: Double) {}
    open fun onStop(e: Engine) {}
}

private fun lerp(a: Double, b: Double, x: Double) = a + (b - a) * x.coerceIn(0.0, 1.0)

object Scenarios {
    fun all(): List<Scenario> = listOf(
        object : Scenario(1, "Démarrage", "Batterie chargée, moteur à l'arrêt, températures normales.", 10.0) {
            override fun onBegin(e: Engine) { e.reset(); e.running = true; e.setSoc(100.0); t0 = e.t }
        },
        object : Scenario(2, "Accélération", "Montée progressive des RPM, vitesse, courant et puissance.", 25.0) {
            override fun onUpdate(e: Engine, t: Double, dt: Double) { e.throttle = lerp(0.0, 0.8, t / 12.0) }
            override fun onStop(e: Engine) { e.throttle = 0.3 }
        },
        object : Scenario(3, "Décélération", "Départ à 40 km/h, lâcher puis freinage doux.", 20.0) {
            override fun onBegin(e: Engine) { e.setSpeedState(40.0) }
            override fun onUpdate(e: Engine, t: Double, dt: Double) { e.throttle = if (t < 5) 0.0 else -0.15 }
        },
        object : Scenario(4, "Batterie faible", "Charge 12 % → 3 %, tension qui chute.", 60.0) {
            override fun onBegin(e: Engine) { e.setSoc(12.0) }
            override fun onUpdate(e: Engine, t: Double, dt: Double) { e.throttle = 0.25; e.setSoc(lerp(12.0, 3.0, t / 55.0)) }
        },
        object : Scenario(5, "Surchauffe", "Températures moteur (→140 °C) et MOSFET (→108 °C) en hausse.", 60.0) {
            override fun onBegin(e: Engine) { e.throttle = 0.5 }
            override fun onUpdate(e: Engine, t: Double, dt: Double) {
                e.setOverride("temp_motor", lerp(40.0, 140.0, t / 50.0)); e.setOverride("temp_fet", lerp(45.0, 108.0, t / 50.0))
            }
            override fun onStop(e: Engine) { e.clearOverride("temp_motor"); e.clearOverride("temp_fet"); e.throttle = 0.0 }
        },
        object : Scenario(6, "Forte accélération", "Plein gaz : puissance et courant maximaux.", 20.0) {
            override fun onUpdate(e: Engine, t: Double, dt: Double) { e.throttle = if (t < 14) 1.0 else 0.0 }
            override fun onStop(e: Engine) { e.throttle = 0.0 }
        },
        object : Scenario(7, "Freinage régénératif", "35 km/h puis régénération : courant batterie négatif.", 25.0) {
            override fun onBegin(e: Engine) { e.setSpeedState(35.0) }
            override fun onUpdate(e: Engine, t: Double, dt: Double) { e.throttle = if (t < 3) 0.2 else -0.7 }
        },
        FaultsScenario(),
        object : Scenario(9, "Perte de connexion", "Coupe les réponses 8 s (à t=4 s) puis rétablit la liaison.", 20.0) {
            override fun onBegin(e: Engine) { e.throttle = 0.3 }
            override fun onUpdate(e: Engine, t: Double, dt: Double) { e.link.up = !(t >= 4.0 && t < 12.0) }
            override fun onStop(e: Engine) { e.link.up = true; e.throttle = 0.0 }
        }
    )
}

class FaultsScenario : Scenario(8, "Défauts contrôleur",
    "Surtension, sous-tension, surchauffe, surintensité, défaut de communication, erreur moteur (6 s chacun).", 42.0) {
    private val steps = listOf("Surtension", "Sous-tension", "Surchauffe MOSFET", "Surintensité", "Défaut de communication", "Erreur moteur")
    private val codes = listOf(Vesc.FAULT_OVER_VOLTAGE, Vesc.FAULT_UNDER_VOLTAGE, Vesc.FAULT_OVER_TEMP_FET,
        Vesc.FAULT_ABS_OVER_CURRENT, 0, Vesc.FAULT_UNBALANCED_CURRENTS)
    private var idx = -1

    private fun clear(e: Engine) {
        e.faultCode = 0
        e.clearOverride("v_in"); e.clearOverride("temp_fet"); e.clearOverride("i_batt")
        e.link.dropRate = 0.0; e.link.crcCorruptRate = 0.0
    }

    override fun onBegin(e: Engine) { e.throttle = 0.3; idx = -1 }
    override fun onUpdate(e: Engine, t: Double, dt: Double) {
        val i = (t / 6).toInt()
        if (i >= steps.size) { clear(e); return }
        if (i != idx) {
            clear(e); idx = i; current = steps[i]
            val p = e.preset
            when (i) {
                0 -> e.setOverride("v_in", p.max * 1.12)
                1 -> e.setOverride("v_in", p.min * 0.85)
                2 -> e.setOverride("temp_fet", 112.0)
                3 -> e.setOverride("i_batt", p.maxBattA * 3.0)
                4 -> { e.link.dropRate = 0.5; e.link.crcCorruptRate = 0.3 }
            }
            if (codes[i] != 0) e.faultCode = codes[i]
        }
    }
    override fun onStop(e: Engine) { clear(e); e.throttle = 0.0 }
}
