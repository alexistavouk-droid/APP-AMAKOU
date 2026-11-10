package com.vescsim.app

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

data class BatteryPreset(
    val name: String, val nominal: Double, val max: Double, val min: Double, val ah: Double,
    val maxMotorA: Double, val maxBattA: Double, val kt: Double, val wheelM: Double, val massKg: Double
)

val PRESETS = listOf(
    BatteryPreset("36 V", 36.0, 42.0, 30.0, 10.0, 30.0, 20.0, 0.55, 0.254, 105.0),
    BatteryPreset("48 V", 48.0, 54.6, 39.0, 15.0, 40.0, 25.0, 0.55, 0.254, 105.0),
    BatteryPreset("52 V", 52.0, 58.8, 42.0, 18.0, 45.0, 30.0, 0.55, 0.254, 105.0),
    BatteryPreset("60 V", 60.0, 67.2, 48.0, 20.0, 55.0, 40.0, 0.55, 0.254, 105.0),
    BatteryPreset("72 V", 72.0, 84.0, 60.0, 30.0, 70.0, 50.0, 0.9, 0.30, 170.0),
    BatteryPreset("84 V", 84.0, 100.8, 72.0, 40.0, 90.0, 60.0, 0.9, 0.30, 170.0)
)

class LinkFaults {
    @Volatile var up = true
    @Volatile var dropRate = 0.0
    @Volatile var crcCorruptRate = 0.0
}

class Engine(preset: BatteryPreset = PRESETS[1]) {
    // --- configuration
    var preset: BatteryPreset = preset; private set
    var polePairs = 15
    var controllerId = 0
    var fwMajor = 7
    var fwMinor = 1
    var hwName = "VESC SIMULATOR"
    val link = LinkFaults()

    @Volatile var running = false
    @Volatile var paused = false
    @Volatile var timeScale = 1.0
    @Volatile var throttle = 0.0
    var scenario: Scenario? = null; private set
    val overrides = HashMap<String, Double>()

    // --- état
    var t = 0.0; private set
    private var v = 0.0
    private var prevV = 0.0
    private var soc = 1.0
    private var tempMotor = 25.0
    private var tempFet = 25.0
    private var whUsed = 0.0; private var whRegen = 0.0; private var ahUsed = 0.0; private var ahRegen = 0.0
    private var distanceM = 0.0; private var tach = 0.0; private var tachAbs = 0.0
    @Volatile var faultCode = 0
    private var autoFault = 0
    private var tel = Telemetry()

    var rInt = 0.06
    var regenA = 0.0
    var initSoc = 1.0
    private val rPhase = 0.08
    private val maxRegenA get() = if (regenA > 0) regenA else preset.maxMotorA * 0.4
    private val mass get() = preset.massKg

    init { reset() }

    // ---- batterie
    private fun ocvFraction(s: Double): Double {
        val pts = doubleArrayOf(0.0, 0.0, 0.05, 0.12, 0.10, 0.22, 0.20, 0.38, 0.30, 0.48, 0.50, 0.62, 0.70, 0.76, 0.90, 0.92, 1.0, 1.0)
        val x = s.coerceIn(0.0, 1.0)
        var i = 0
        while (i + 3 < pts.size) {
            if (x <= pts[i + 2]) return pts[i + 1] + (pts[i + 3] - pts[i + 1]) * (x - pts[i]) / (pts[i + 2] - pts[i])
            i += 2
        }
        return 1.0
    }

    private fun ocv() = preset.min + (preset.max - preset.min) * ocvFraction(soc)
    private fun terminalV(i: Double) = max(0.0, ocv() - i * rInt)

    // ---- commandes
    @Synchronized fun applyPreset(p: BatteryPreset) { preset = p; reset() }

    @Synchronized fun reset() {
        t = 0.0; v = 0.0; prevV = 0.0; throttle = 0.0; overrides.clear(); faultCode = 0; autoFault = 0
        tempMotor = 25.0; tempFet = 25.0; whUsed = 0.0; whRegen = 0.0; ahUsed = 0.0; ahRegen = 0.0
        distanceM = 0.0; tach = 0.0; tachAbs = 0.0; soc = initSoc
        link.up = true; link.dropRate = 0.0; link.crcCorruptRate = 0.0
        scenario = null
        tel = Telemetry().also { it.controllerId = controllerId }
        step(0.0, true)
    }

    @Synchronized fun setOverride(key: String, value: Double) {
        overrides[key] = value
        if (key == "rpm") overrides.remove("speed") else if (key == "speed") overrides.remove("rpm")
    }
    @Synchronized fun clearOverride(key: String?) { if (key == null) overrides.clear() else overrides.remove(key) }
    @Synchronized fun setSoc(pct: Double) { soc = (pct / 100.0).coerceIn(0.0, 1.0) }
    @Synchronized fun setSpeedState(kmh: Double) { v = max(0.0, kmh / 3.6); prevV = v }
    @Synchronized fun setScenario(s: Scenario?) {
        scenario?.stop(this)
        scenario = s
        s?.begin(this)
    }
    @Synchronized fun applyReferenceVector() {
        throttle = 0.0
        setOverride("rpm", 500.0); setOverride("v_in", 48.0); setOverride("i_batt", 10.0)
        setOverride("temp_motor", 55.0); setOverride("temp_fet", 40.0)
        setSoc(50.0); faultCode = 0
    }

    private fun rpmToSpeed(rpm: Double) = rpm / 60.0 * PI * preset.wheelM

    private fun derate(): Pair<Double, String> {
        val dF = 1.0 - ((tempFet - 80.0) / 20.0).coerceIn(0.0, 1.0)
        val dM = 1.0 - ((tempMotor - 100.0) / 30.0).coerceIn(0.0, 1.0)
        val dV = ((terminalV(0.0) - preset.min) / max(1.0, 0.05 * (preset.max - preset.min) + 2.0)).coerceIn(0.2, 1.0)
        val d = min(dF, min(dM, dV))
        return d to (if (d >= 0.999) "NORMAL" else if (d > 0.3) "LIMITATION" else "CRITIQUE")
    }

    @Synchronized
    fun step(dt: Double, force: Boolean = false): Telemetry {
        if ((paused || !running) && !force) return tel
        val p = preset
        val dtS = dt * timeScale
        if (dtS > 0) {
            t += dtS
            scenario?.let {
                it.update(this, t - it.t0, dtS)
                if (it.finished) { it.stop(this); scenario = null }
            }
        }
        val (derate, tstate) = derate()
        val faulted = faultCode != 0 || autoFault != 0
        val thr = if (faulted) 0.0 else throttle
        val ov = overrides
        val vForced: Double? = ov["rpm"]?.let { rpmToSpeed(it) } ?: ov["speed"]?.let { it / 3.6 }
        val r = p.wheelM / 2.0
        val ktWheel = p.kt / r
        val fRoll = if (v > 0.05) 0.012 * mass * 9.81 else 0.0
        val fDrag = 0.5 * 1.2 * 0.45 * v * v

        var iq = if (thr >= 0) thr * p.maxMotorA * derate else thr * maxRegenA * (if (v > 0.5) 1.0 else 0.0)
        var omega = v / r
        var duty = min(1.0, omega * p.kt * 0.9 / max(terminalV(0.0), 1.0))
        if (iq > 0) iq *= ((0.95 - duty) / 0.10).coerceIn(0.0, 1.0)
        val vb = max(terminalV(0.0), 1.0)
        var pMech = iq * ktWheel * v
        var pElec = pMech + 1.5 * rPhase * iq * iq + 5.0
        if (pElec > 0) {
            val lim = min(p.maxBattA * vb, p.maxBattA * p.nominal * derate)
            if (pElec > lim) iq *= max(0.0, lim / pElec)
        }
        if (vForced != null) {
            val a = if (dtS > 1e-9) (vForced - prevV) / dtS else 0.0
            val fNeed = fRoll + fDrag + mass * a
            v = max(0.0, vForced)
            iq = (fNeed / ktWheel).coerceIn(-maxRegenA, p.maxMotorA)
        } else {
            val a = (iq * ktWheel - fRoll - fDrag) / mass
            if (dtS > 0) {
                v = max(0.0, v + a * dtS)
                if (v < 0.02 && iq * ktWheel <= fRoll) v = 0.0
            }
        }
        prevV = v

        val rpmMech = v / (PI * p.wheelM) * 60.0
        pMech = iq * ktWheel * v
        val pLoss = 1.5 * rPhase * iq * iq
        pElec = pMech + pLoss + (if (faulted && iq == 0.0) 0.0 else 5.0)
        var vTerm = terminalV(0.0)
        var iBatt = pElec / max(vTerm, 1.0)
        vTerm = terminalV(iBatt); iBatt = pElec / max(vTerm, 1.0); vTerm = terminalV(iBatt)
        omega = v / r
        duty = min(1.0, omega * p.kt * 0.9 / max(vTerm, 1.0))
        ov["i_batt"]?.let { iBatt = it; iq = (it / max(duty, 0.1)).coerceIn(-maxRegenA * 2, p.maxMotorA * 2); vTerm = terminalV(it) }
        val vMeas = ov["v_in"] ?: vTerm
        val pBatt = iBatt * vMeas

        if (dtS > 0) {
            soc = (soc - iBatt * dtS / 3600.0 / p.ah).coerceIn(0.0, 1.0)
            val e = abs(pBatt) * dtS / 3600.0
            val q = abs(iBatt) * dtS / 3600.0
            if (iBatt >= 0) { whUsed += e; ahUsed += q } else { whRegen += e; ahRegen += q }
            distanceM += v * dtS
            val dTach = rpmMech * polePairs / 60.0 * 6.0 * dtS
            tach += dTach; tachAbs += abs(dTach)
            val air = 1.0 + 0.08 * (v * 3.6)
            val pFet = 0.015 * iq * iq + 0.02 * abs(iq) * duty * 10 + 1.0
            val tmInf = 25.0 + pLoss * 1.6 / air
            val tfInf = 25.0 + pFet * 1.2 / (1 + 0.02 * air)
            tempMotor += (tmInf - tempMotor) * min(1.0, dtS / 60.0)
            tempFet += (tfInf - tempFet) * min(1.0, dtS / 30.0)
        }
        ov["temp_motor"]?.let { tempMotor = it }
        ov["temp_fet"]?.let { tempFet = it }

        autoFault = when {
            vMeas > p.max * 1.08 -> Vesc.FAULT_OVER_VOLTAGE
            vMeas < p.min * 0.92 -> Vesc.FAULT_UNDER_VOLTAGE
            tempFet > 105 -> Vesc.FAULT_OVER_TEMP_FET
            tempMotor > 140 -> Vesc.FAULT_OVER_TEMP_MOTOR
            else -> 0
        }

        val distKm = distanceM / 1000.0
        val speedKmh = v * 3.6
        val whNet = whUsed - whRegen
        val whKm = if (distKm > 0.05) whNet / distKm else if (speedKmh > 1.0) max(0.0, pBatt) / speedKmh else 0.0
        val x = tel
        x.rpmMech = rpmMech; x.erpm = rpmMech * polePairs; x.speedKmh = speedKmh; x.torqueNm = iq * p.kt
        x.iMotor = iq; x.duty = duty; x.vIn = vMeas; x.iBatt = iBatt; x.powerW = pBatt; x.socPct = soc * 100.0
        x.whUsed = whUsed; x.whRegen = whRegen; x.ahUsed = ahUsed; x.ahRegen = ahRegen; x.whPerKm = whKm
        x.whLeft = soc * p.ah * p.nominal; x.tempFet = tempFet; x.tempMotor = tempMotor
        x.powerLimitPct = derate * 100.0; x.thermalState = tstate
        x.fault = if (faultCode != 0) faultCode else autoFault
        x.distanceKm = distKm; x.odometerM = distanceM; x.tachometer = tach.toLong(); x.tachometerAbs = tachAbs.toLong()
        x.uptimeMs = (t * 1000).toLong(); x.controllerId = controllerId
        // forçages directs de grandeurs de sortie (tout est modifiable depuis l'app)
        ov["i_motor"]?.let { x.iMotor = it; x.torqueNm = it * p.kt }
        ov["duty"]?.let { x.duty = it }
        ov["power_w"]?.let { x.powerW = it }
        ov["wh_per_km"]?.let { x.whPerKm = it }
        ov["distance_km"]?.let { x.distanceKm = it; x.odometerM = it * 1000.0 }
        ov["wh_used"]?.let { x.whUsed = it }
        ov["wh_regen"]?.let { x.whRegen = it }
        ov["soc_pct"]?.let { x.socPct = it; x.whLeft = it / 100.0 * p.ah * p.nominal }
        return x
    }

    @Synchronized fun snapshot(): Telemetry = tel.copy()
    @Synchronized fun forced(key: String): Boolean = overrides.containsKey(key)
    @Synchronized fun forcedValue(key: String): Double? = overrides[key]
}
