package com.vescsim.app

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.os.Build
import org.json.JSONObject

/** État partagé : moteur, journal, BLE, configuration persistante. */
class AppState(val act: Activity) {
    val engine = Engine()
    val log = FrameLog()
    val responder = Responder(engine, log)
    var ble: BleServer? = null
    @Volatile var bleState = "Arrêté"
    var bleName = "VESC SIM"
    private val prefs = act.getSharedPreferences("vescsim", Activity.MODE_PRIVATE)

    init {
        try { prefs.getString("last", null)?.let { applyJson(JSONObject(it)) } } catch (_: Exception) { }
        engine.running = true
    }

    // ---- configuration <-> JSON
    fun toJson(): JSONObject = JSONObject().apply {
        val p = engine.preset
        put("nominal", p.nominal); put("max", p.max); put("min", p.min); put("ah", p.ah)
        put("maxMotorA", p.maxMotorA); put("maxBattA", p.maxBattA); put("kt", p.kt); put("wheelM", p.wheelM); put("massKg", p.massKg)
        put("poles", engine.polePairs * 2); put("rIntMohm", engine.rInt * 1000.0); put("regenA", engine.regenA)
        put("initSoc", engine.initSoc * 100.0); put("controllerId", engine.controllerId)
        put("fwMajor", engine.fwMajor); put("fwMinor", engine.fwMinor); put("hwName", engine.hwName); put("bleName", bleName)
    }

    fun applyJson(j: JSONObject) {
        val d = engine.preset
        engine.polePairs = (j.optInt("poles", engine.polePairs * 2) / 2).coerceAtLeast(1)
        engine.rInt = j.optDouble("rIntMohm", engine.rInt * 1000.0) / 1000.0
        engine.regenA = j.optDouble("regenA", engine.regenA)
        engine.initSoc = j.optDouble("initSoc", engine.initSoc * 100.0) / 100.0
        engine.controllerId = j.optInt("controllerId", engine.controllerId)
        engine.fwMajor = j.optInt("fwMajor", engine.fwMajor); engine.fwMinor = j.optInt("fwMinor", engine.fwMinor)
        engine.hwName = j.optString("hwName", engine.hwName).ifBlank { "VESC SIMULATOR" }
        bleName = j.optString("bleName", bleName).ifBlank { "VESC SIM" }
        engine.applyPreset(BatteryPreset("Perso", j.optDouble("nominal", d.nominal), j.optDouble("max", d.max), j.optDouble("min", d.min),
            j.optDouble("ah", d.ah), j.optDouble("maxMotorA", d.maxMotorA), j.optDouble("maxBattA", d.maxBattA),
            j.optDouble("kt", d.kt), j.optDouble("wheelM", d.wheelM), j.optDouble("massKg", d.massKg)))
        engine.running = true
    }

    fun saveLast() { prefs.edit().putString("last", toJson().toString()).apply() }

    fun profiles(): JSONObject = try { JSONObject(prefs.getString("profiles", "{}")!!) } catch (_: Exception) { JSONObject() }
    fun saveProfile(name: String) { val p = profiles(); p.put(name, toJson()); prefs.edit().putString("profiles", p.toString()).apply() }
    fun deleteProfile(name: String) { val p = profiles(); p.remove(name); prefs.edit().putString("profiles", p.toString()).apply() }
    fun loadProfile(name: String) { profiles().optJSONObject(name)?.let { applyJson(it); saveLast() } }

    // ---- Bluetooth
    fun hasBlePerms() = Build.VERSION.SDK_INT < 31 ||
        (act.checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED &&
            act.checkSelfPermission(Manifest.permission.BLUETOOTH_ADVERTISE) == PackageManager.PERMISSION_GRANTED)

    fun requestPerms() {
        if (Build.VERSION.SDK_INT >= 31 && !hasBlePerms())
            act.requestPermissions(arrayOf(Manifest.permission.BLUETOOTH_CONNECT, Manifest.permission.BLUETOOTH_ADVERTISE), 1)
    }

    fun toggleBle() {
        val b = ble
        if (b != null && (b.isAdvertising || b.isConnected)) { b.stop(); return }
        if (!hasBlePerms()) { requestPerms(); bleState = "Autorisations Bluetooth requises — réessayez"; return }
        val srv = BleServer(act, responder) { st -> bleState = st }
        val err = srv.start(bleName)
        if (err != null) { bleState = err; return }
        ble = srv
    }

    val bleOn get() = ble?.let { it.isAdvertising || it.isConnected } == true
    fun shutdown() { ble?.stop() }
}
