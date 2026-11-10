package com.vescsim.app

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** État partagé : moteur, journal, BLE, configuration persistante. */
class AppState private constructor(private val ctx: Context) {
    lateinit var act: Activity
    val engine = Engine()
    val log = FrameLog()
    val responder = Responder(engine, log)
    var ble: BleServer? = null
    @Volatile var bleState = "Arrêté"
    var bleName = "VESC SIM"
    private val prefs = ctx.getSharedPreferences("vescsim", Activity.MODE_PRIVATE)

    init {
        try { prefs.getString("last", null)?.let { applyJson(JSONObject(it)) } } catch (_: Exception) { }
        engine.running = true
        var last = System.nanoTime()
        Executors.newSingleThreadScheduledExecutor().scheduleAtFixedRate({
            try { val now = System.nanoTime(); engine.step(((now - last) / 1e9).coerceAtMost(0.2)); last = now } catch (_: Throwable) { }
        }, 20, 20, TimeUnit.MILLISECONDS)
    }

    companion object {
        @Volatile private var inst: AppState? = null
        fun get(a: Activity): AppState { val s = inst ?: AppState(a.applicationContext).also { inst = it }; s.act = a; return s }
        fun peek(): AppState? = inst
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
        val need = ArrayList<String>()
        if (Build.VERSION.SDK_INT >= 31 && !hasBlePerms()) { need += Manifest.permission.BLUETOOTH_CONNECT; need += Manifest.permission.BLUETOOTH_ADVERTISE }
        if (Build.VERSION.SDK_INT >= 33 && act.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            need += Manifest.permission.POST_NOTIFICATIONS
        if (need.isNotEmpty()) act.requestPermissions(need.toTypedArray(), 1)
    }

    fun toggleBle() {
        val b = ble
        if (b != null && (b.isAdvertising || b.isConnected)) { stopBle(); return }
        if (!hasBlePerms()) { requestPerms(); bleState = "Autorisations Bluetooth requises — réessayez"; return }
        val srv = BleServer(ctx, responder) { st -> bleState = st }
        val err = srv.start(bleName)
        if (err != null) { bleState = err; return }
        ble = srv
        SimService.start(ctx)
    }

    fun stopBle() { ble?.stop(); SimService.stop(ctx) }

    val bleOn get() = ble?.let { it.isAdvertising || it.isConnected } == true
}
