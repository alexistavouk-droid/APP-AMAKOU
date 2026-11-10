package com.vescsim.app

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.Spinner
import android.widget.TextView
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit

class MainActivity : Activity() {
    private val BG = Color.parseColor("#0f1419"); private val PANEL = Color.parseColor("#171d25")
    private val ACCENT = Color.parseColor("#00b4d8"); private val OK = Color.parseColor("#2ecc71")
    private val BAD = Color.parseColor("#ff4d4f"); private val WARN = Color.parseColor("#f5a623")
    private val MUTED = Color.parseColor("#8b98a8")

    private val engine = Engine()
    private val log = FrameLog()
    private val responder = Responder(engine, log)
    private var ble: BleServer? = null
    private var bleState = "Arrêté"
    private val ui = Handler(Looper.getMainLooper())
    private var sched: ScheduledExecutorService? = null

    private lateinit var status: TextView
    private lateinit var telem: TextView
    private lateinit var logView: TextView
    private lateinit var faultBanner: TextView
    private lateinit var bleBtn: Button
    private lateinit var scenInfo: TextView
    private lateinit var nameEdit: EditText
    private val scenarios = Scenarios.all()
    private val sliders = ArrayList<Pair<CheckBox, SeekBar>>()

    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), dp(12), dp(12), dp(24)); setBackgroundColor(BG) }
        setContentView(ScrollView(this).apply { setBackgroundColor(BG); addView(root) })

        root.addView(text("VESC SIMULATOR", 20f, Color.WHITE, true))
        root.addView(text("Faux module Bluetooth VESC — télémétrie seule", 12f, MUTED))
        status = text("", 13f, Color.WHITE).also { it.setPadding(0, dp(8), 0, dp(8)) }; root.addView(status)
        faultBanner = text("", 14f, Color.WHITE, true).also { it.setBackgroundColor(BAD); it.setPadding(dp(8), dp(6), dp(8), dp(6)); it.visibility = View.GONE }
        root.addView(faultBanner)

        // --- Bluetooth
        root.addView(section("Bluetooth (BLE — Nordic UART)"))
        nameEdit = EditText(this).apply { setText("VESC SIM"); setTextColor(Color.WHITE); setSingleLine() }
        root.addView(row(text("Nom BLE annoncé", 12f, MUTED), nameEdit))
        bleBtn = button("Démarrer le Bluetooth") { toggleBle() }
        root.addView(bleBtn)

        // --- simulation
        root.addView(section("Simulation"))
        root.addView(row(
            button("▶ START") { engine.running = true; engine.paused = false },
            button("■ STOP") { engine.running = false; engine.throttle = 0.0 },
            button("⏸ PAUSE") { engine.paused = !engine.paused },
            button("↺ RESET") { resetAll() }))
        val prof = Spinner(this); prof.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, PRESETS.map { "Batterie ${it.name}" })
        prof.setSelection(1)
        prof.onItemSelectedListener = sel { i -> if (PRESETS[i] !== engine.preset) { engine.applyPreset(PRESETS[i]); engine.running = true; releaseSliders() } }
        root.addView(prof)
        val speed = Spinner(this); speed.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, listOf("Mode ralenti ×0,25", "Mode normal ×1", "Mode accéléré ×4"))
        speed.setSelection(1)
        speed.onItemSelectedListener = sel { i -> engine.timeScale = doubleArrayOf(0.25, 1.0, 4.0)[i] }
        root.addView(speed)

        // --- télémétrie
        root.addView(section("Télémétrie envoyée à l'écran"))
        telem = text("", 14f, Color.WHITE).also { it.typeface = Typeface.MONOSPACE; it.setBackgroundColor(PANEL); it.setPadding(dp(10), dp(8), dp(10), dp(8)) }
        root.addView(telem)

        // --- scénarios
        root.addView(section("Scénarios"))
        val sc = Spinner(this); sc.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, scenarios.map { "${it.id}. ${it.name}" })
        root.addView(sc)
        scenInfo = text("", 12f, MUTED); root.addView(scenInfo)
        root.addView(row(
            button("▶ Lancer") { engine.running = true; engine.paused = false; Scenarios.all()[sc.selectedItemPosition].let { engine.setScenario(it) } },
            button("■ Arrêter") { engine.setScenario(null); engine.link.up = true; engine.link.dropRate = 0.0; engine.link.crcCorruptRate = 0.0 }))

        // --- forçages
        root.addView(section("Forçage en direct (transmis immédiatement)"))
        addSlider(root, "rpm", "RPM moteur", 0.0, 1500.0, 300.0, "tr/min")
        addSlider(root, "speed", "Vitesse", 0.0, 80.0, 25.0, "km/h")
        addSlider(root, "v_in", "Tension batt.", 20.0, 110.0, 48.0, "V")
        addSlider(root, "i_batt", "Intensité batt.", -30.0, 80.0, 10.0, "A")
        addSlider(root, "temp_motor", "Temp. moteur", 0.0, 160.0, 50.0, "°C")
        addSlider(root, "temp_fet", "Temp. MOSFET", 0.0, 130.0, 45.0, "°C")
        root.addView(simpleSlider("Niveau batterie", 0, 100, 100, "%") { engine.setSoc(it.toDouble()) })
        root.addView(simpleSlider("Accélérateur (− = frein)", -100, 100, 0, "%") { engine.throttle = it / 100.0 })
        val fault = Spinner(this)
        val codes = listOf(0 to "Défaut : aucun", 1 to "Surtension", 2 to "Sous-tension", 5 to "Surchauffe MOSFET", 4 to "Surintensité", 17 to "Erreur moteur")
        fault.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, codes.map { it.second })
        fault.onItemSelectedListener = sel { i -> engine.faultCode = codes[i].first }
        root.addView(fault)

        // --- dashboard test
        root.addView(section("DASHBOARD TEST"))
        root.addView(row(
            button("Vecteur de référence") { engine.running = true; engine.applyReferenceVector() },
            button("Libérer") { releaseSliders() }))
        root.addView(button("Test déconnexion (6 s)") {
            engine.link.up = false; log.info("Test déconnexion : liaison coupée 6 s", "WARN")
            ui.postDelayed({ engine.link.up = true; log.info("Test déconnexion : liaison rétablie") }, 6000)
        })
        root.addView(text("Référence : 500 tr/min méca., 48,0 V, 10,0 A, moteur 55 °C, MOSFET 40 °C, batterie 50 %. " +
                "Comparez avec l'écran du tableau de bord.", 12f, MUTED))

        // --- journal
        root.addView(section("Journal des trames"))
        logView = text("", 10f, Color.WHITE).also { it.typeface = Typeface.MONOSPACE; it.setBackgroundColor(PANEL); it.setPadding(dp(8), dp(6), dp(8), dp(6)) }
        root.addView(logView)
        root.addView(button("Effacer le journal") { log.clear() })

        engine.running = true
        requestPerms()
    }

    override fun onStart() {
        super.onStart()
        sched = Executors.newSingleThreadScheduledExecutor().also {
            var last = System.nanoTime()
            it.scheduleAtFixedRate({
                val now = System.nanoTime(); engine.step(((now - last) / 1e9).coerceAtMost(0.2)); last = now
            }, 20, 20, TimeUnit.MILLISECONDS)
        }
        ui.post(refresh)
    }

    override fun onStop() {
        super.onStop()
        ui.removeCallbacks(refresh)
        sched?.shutdownNow()
    }

    override fun onDestroy() { ble?.stop(); super.onDestroy() }

    private val refresh = object : Runnable {
        override fun run() { update(); ui.postDelayed(this, 150) }
    }

    private fun update() {
        val t = engine.snapshot()
        val since = if (log.lastRxMs == 0L) -1.0 else (System.currentTimeMillis() - log.lastRxMs) / 1000.0
        val linked = since in 0.0..3.0 && engine.link.up
        val simState = if (!engine.running) "STOPPED" else if (engine.paused) "PAUSE" else "RUNNING"
        status.text = "VESC : ${if (linked) "CONNECTÉ" else "DÉCONNECTÉ"}   Simulation : $simState\n" +
            "BLE : $bleState\nRequêtes : %.1f Hz   RX %d  TX %d  CRC %d  bloquées %d  inconnues %d\nTemps simulé : %d s"
                .format(log.rateHz(), log.rx, log.tx, log.crcErrors, log.blocked, log.unknown, engine.t.toInt())
        status.setTextColor(if (linked) OK else WARN)
        if (t.fault != 0) { faultBanner.text = "DÉFAUT : ${Vesc.FAULT_NAMES[t.fault] ?: t.fault} (code ${t.fault})"; faultBanner.visibility = View.VISIBLE }
        else faultBanner.visibility = View.GONE
        telem.text = "RPM méca.   %7.0f tr/min\nERPM envoyé %7.0f\nVitesse     %7.1f km/h\nTension     %7.1f V\nCourant bat %+7.1f A\n".format(t.rpmMech, t.erpm, t.speedKmh, t.vIn, t.iBatt) +
            "Courant mot %+7.1f A\nPuissance   %+7.0f W\nTemp MOSFET %7.1f °C\nTemp moteur %7.1f °C\n".format(t.iMotor, t.powerW, t.tempFet, t.tempMotor) +
            "Batterie    %7.1f %%\nConso       %7.1f Wh/km\nDistance    %7.3f km\nWh conso.   %7.2f Wh\nLimitation  %7.0f %% (${t.thermalState})".format(t.socPct, t.whPerKm, t.distanceKm, t.whUsed, t.powerLimitPct)
        val s = engine.scenario
        scenInfo.text = if (s == null) "Aucun scénario actif" else "En cours : ${s.name} (%d/%d s) %s".format((engine.t - s.t0).toInt(), s.duration.toInt(), s.current)
        logView.text = log.tail(40).joinToString("\n") { e ->
            val tm = java.text.SimpleDateFormat("HH:mm:ss.SSS", java.util.Locale.US).format(java.util.Date(e.ts))
            if (e.dir == "RX" || e.dir == "TX") {
                val h = if (e.hex.length > 48) e.hex.substring(0, 48) + "…" else e.hex
                "$tm ${e.dir} ${e.cmdName.removePrefix("COMM_")} len=${e.size} crc=%04X/%04X %s\n   %s".format(e.crcCalc ?: 0, e.crcRx ?: 0, if (e.valid == true) "OK" else "KO", h)
            } else "$tm [${e.dir}] ${e.msg}"
        }
    }

    // ---------------------------------------------------------------- actions
    private fun toggleBle() {
        val b = ble
        if (b != null && (b.isAdvertising || b.isConnected)) { b.stop(); bleBtn.text = "Démarrer le Bluetooth"; return }
        if (!hasBlePerms()) { requestPerms(); bleState = "Autorisations Bluetooth requises"; return }
        val srv = BleServer(this, responder) { st -> bleState = st }
        val err = srv.start(nameEdit.text.toString().ifBlank { "VESC SIM" })
        if (err != null) { bleState = err; return }
        ble = srv
        bleBtn.text = "Arrêter le Bluetooth"
    }

    private fun resetAll() { engine.setScenario(null); engine.reset(); releaseSliders(); engine.running = true }

    private fun releaseSliders() { for ((c, _) in sliders) c.isChecked = false; engine.clearOverride(null) }

    private fun hasBlePerms(): Boolean =
        Build.VERSION.SDK_INT < 31 || (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED &&
            checkSelfPermission(Manifest.permission.BLUETOOTH_ADVERTISE) == PackageManager.PERMISSION_GRANTED)

    private fun requestPerms() {
        if (Build.VERSION.SDK_INT >= 31 && !hasBlePerms())
            requestPermissions(arrayOf(Manifest.permission.BLUETOOTH_CONNECT, Manifest.permission.BLUETOOTH_ADVERTISE), 1)
    }

    // ---------------------------------------------------------------- UI helpers
    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun text(s: String, size: Float, color: Int, bold: Boolean = false) = TextView(this).apply {
        text = s; textSize = size; setTextColor(color); if (bold) typeface = Typeface.DEFAULT_BOLD
    }

    private fun section(s: String) = text(s.uppercase(), 12f, ACCENT, true).also { it.setPadding(0, dp(16), 0, dp(4)) }

    private fun button(label: String, onClick: () -> Unit) = Button(this).apply {
        text = label; setAllCaps(false); setOnClickListener { onClick() }
    }

    private fun row(vararg v: View) = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        for (x in v) addView(x, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
    }

    private fun sel(f: (Int) -> Unit) = object : AdapterView.OnItemSelectedListener {
        override fun onItemSelected(p: AdapterView<*>?, v: View?, pos: Int, id: Long) = f(pos)
        override fun onNothingSelected(p: AdapterView<*>?) {}
    }

    private fun addSlider(root: LinearLayout, key: String, label: String, lo: Double, hi: Double, init: Double, unit: String) {
        val chk = CheckBox(this).apply { text = label; setTextColor(Color.WHITE) }
        val value = text("", 12f, MUTED)
        val sb = SeekBar(this).apply { max = 1000; progress = (((init - lo) / (hi - lo)) * 1000).toInt() }
        fun v() = lo + (hi - lo) * sb.progress / 1000.0
        fun apply() { value.text = "%.1f %s".format(v(), unit); if (chk.isChecked) engine.setOverride(key, v()) }
        sb.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(s: SeekBar?, p: Int, fromUser: Boolean) { if (fromUser) chk.isChecked = true; apply() }
            override fun onStartTrackingTouch(s: SeekBar?) {}
            override fun onStopTrackingTouch(s: SeekBar?) {}
        })
        chk.setOnCheckedChangeListener { _, on -> if (on) apply() else engine.clearOverride(key) }
        value.text = "%.1f %s".format(v(), unit)
        root.addView(row(chk, value))
        root.addView(sb)
        sliders.add(chk to sb)
    }

    private fun simpleSlider(label: String, lo: Int, hi: Int, init: Int, unit: String, onChange: (Int) -> Unit): View {
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val tv = text("$label : $init $unit", 12f, Color.WHITE)
        val sb = SeekBar(this).apply { max = hi - lo; progress = init - lo }
        sb.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(s: SeekBar?, p: Int, fromUser: Boolean) { tv.text = "$label : ${p + lo} $unit"; if (fromUser) onChange(p + lo) }
            override fun onStartTrackingTouch(s: SeekBar?) {}
            override fun onStopTrackingTouch(s: SeekBar?) {}
        })
        box.addView(tv); box.addView(sb)
        return box
    }
}
