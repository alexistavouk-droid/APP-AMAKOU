package com.vescsim.app

class Telemetry {
    var rpmMech = 0.0; var erpm = 0.0; var speedKmh = 0.0; var torqueNm = 0.0
    var iMotor = 0.0; var iD = 0.0; var duty = 0.0
    var vIn = 0.0; var iBatt = 0.0; var powerW = 0.0; var socPct = 100.0
    var whUsed = 0.0; var whRegen = 0.0; var ahUsed = 0.0; var ahRegen = 0.0
    var whPerKm = 0.0; var whLeft = 0.0
    var tempFet = 25.0; var tempMotor = 25.0; var powerLimitPct = 100.0; var thermalState = "NORMAL"
    var fault = 0
    var distanceKm = 0.0; var odometerM = 0.0; var tachometer = 0L; var tachometerAbs = 0L
    var uptimeMs = 0L; var controllerId = 0

    fun copy(): Telemetry {
        val t = Telemetry()
        t.rpmMech = rpmMech; t.erpm = erpm; t.speedKmh = speedKmh; t.torqueNm = torqueNm
        t.iMotor = iMotor; t.iD = iD; t.duty = duty; t.vIn = vIn; t.iBatt = iBatt; t.powerW = powerW
        t.socPct = socPct; t.whUsed = whUsed; t.whRegen = whRegen; t.ahUsed = ahUsed; t.ahRegen = ahRegen
        t.whPerKm = whPerKm; t.whLeft = whLeft; t.tempFet = tempFet; t.tempMotor = tempMotor
        t.powerLimitPct = powerLimitPct; t.thermalState = thermalState; t.fault = fault
        t.distanceKm = distanceKm; t.odometerM = odometerM; t.tachometer = tachometer
        t.tachometerAbs = tachometerAbs; t.uptimeMs = uptimeMs; t.controllerId = controllerId
        return t
    }

    /** Valeurs au format des réponses COMM_GET_VALUES (unités du firmware). */
    fun vescValues(): Map<String, Double> = mapOf(
        "temp_fet" to tempFet, "temp_motor" to tempMotor,
        "avg_motor_current" to iMotor, "avg_input_current" to iBatt,
        "avg_id" to iD, "avg_iq" to iMotor, "duty" to duty, "rpm" to erpm, "v_in" to vIn,
        "amp_hours" to ahUsed, "amp_hours_charged" to ahRegen, "watt_hours" to whUsed,
        "watt_hours_charged" to whRegen, "tachometer" to tachometer.toDouble(),
        "tachometer_abs" to tachometerAbs.toDouble(), "fault" to fault.toDouble(), "pid_pos" to 0.0,
        "controller_id" to controllerId.toDouble(),
        "temp_mos1" to tempFet, "temp_mos2" to tempFet, "temp_mos3" to tempFet,
        "avg_vd" to 0.0, "avg_vq" to duty * vIn * 0.577, "status" to 0.0
    )

    /** Valeurs COMM_GET_VALUES_SETUP : vitesse en m/s, niveau batterie 0..1, distance en m. */
    fun setupValues(): Map<String, Double> = mapOf(
        "temp_fet" to tempFet, "temp_motor" to tempMotor,
        "current_tot" to iMotor, "current_in_tot" to iBatt, "duty" to duty, "rpm" to erpm,
        "speed" to speedKmh / 3.6, "v_in" to vIn, "battery_level" to socPct / 100.0,
        "amp_hours" to ahUsed, "amp_hours_charged" to ahRegen, "watt_hours" to whUsed,
        "watt_hours_charged" to whRegen, "distance" to distanceKm * 1000.0, "distance_abs" to distanceKm * 1000.0,
        "pid_pos" to 0.0, "fault" to fault.toDouble(), "controller_id" to controllerId.toDouble(),
        "num_vescs" to 1.0, "wh_batt_left" to whLeft, "odometer" to odometerM.toLong().toDouble(),
        "uptime_ms" to uptimeMs.toDouble()
    )
}
