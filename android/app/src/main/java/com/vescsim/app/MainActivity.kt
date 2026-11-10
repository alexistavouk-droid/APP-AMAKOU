package com.vescsim.app

import android.app.Activity
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit

class MainActivity : Activity() {
    private lateinit var s: AppState
    private val ui = Handler(Looper.getMainLooper())
    private var sched: ScheduledExecutorService? = null
    private lateinit var pages: List<Page>
    private val navItems = ArrayList<TextView>()
    private lateinit var container: FrameLayout
    private lateinit var linkChip: TextView
    private lateinit var simChip: TextView
    private lateinit var bleChip: TextView
    private var current = 0

    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        window.statusBarColor = C.BG; window.navigationBarColor = C.PANEL
        s = AppState(this)
        pages = listOf(DashboardPage(s), ControlPage(s), SettingsPage(s), ScenarioPage(s), DiagPage(s))

        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(C.BG) }
        setContentView(root)

        // en-tête
        val head = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(12), dp(14), dp(8)) }
        val title = hbox()
        title.addView(label("⚡ ", 22f, C.WARN, true))
        title.addView(label("VESC SIM", 22f, C.TEXT, true))
        title.addView(label("  PRO", 22f, C.CYAN, true))
        val sp = View(this); title.addView(sp, LinearLayout.LayoutParams(0, 1, 1f))
        bleChip = chip("BLE", C.OK) { s.toggleBle() }
        title.addView(bleChip)
        head.addView(title)
        val chips = hbox().also { it.setPadding(0, dp(8), 0, 0) }
        linkChip = chip("DÉCONNECTÉ", C.BAD); simChip = chip("RUNNING", C.OK)
        chips.addW(linkChip, 1f, dp(3)); chips.addW(simChip, 1f, dp(3))
        head.addView(chips)
        root.addView(head)

        container = FrameLayout(this)
        root.addView(container, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))

        // navigation basse
        val nav = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setBackgroundColor(C.PANEL); setPadding(0, dp(4), 0, dp(4)) }
        val names = listOf("◉\nTableau", "🎚\nContrôle", "⚙\nRéglages", "▶\nScénarios", "🔍\nDiagnostic")
        for ((i, n) in names.withIndex()) {
            val tv = TextView(this).apply {
                text = n; textSize = 11f; gravity = Gravity.CENTER; setTextColor(C.MUTED); setPadding(0, dp(6), 0, dp(6))
                setOnClickListener { show(i) }
            }
            navItems.add(tv); nav.addView(tv, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        }
        root.addView(nav)
        for (p in pages) container.addView(p.view, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        show(0)
        s.requestPerms()
    }

    private fun show(i: Int) {
        current = i
        pages.forEachIndexed { k, p -> p.view.visibility = if (k == i) View.VISIBLE else View.GONE; p.visible = k == i }
        navItems.forEachIndexed { k, t -> t.setTextColor(if (k == i) C.CYAN else C.MUTED) }
        (pages[2] as SettingsPage).let { if (i == 2) it.onShow() }
    }

    override fun onStart() {
        super.onStart()
        sched = Executors.newSingleThreadScheduledExecutor().also {
            var last = System.nanoTime()
            it.scheduleAtFixedRate({
                val now = System.nanoTime(); s.engine.step(((now - last) / 1e9).coerceAtMost(0.2)); last = now
            }, 20, 20, TimeUnit.MILLISECONDS)
        }
        ui.post(refresh)
    }

    override fun onStop() { super.onStop(); ui.removeCallbacks(refresh); sched?.shutdownNow() }
    override fun onDestroy() { s.shutdown(); super.onDestroy() }

    private val refresh = object : Runnable {
        override fun run() { update(); ui.postDelayed(this, 120) }
    }

    private fun update() {
        val e = s.engine
        val t = e.snapshot()
        val since = if (s.log.lastRxMs == 0L) -1.0 else (System.currentTimeMillis() - s.log.lastRxMs) / 1000.0
        val linked = since in 0.0..3.0 && e.link.up
        setChip(linkChip, if (linked) "VESC CONNECTÉ · %.1f Hz".format(s.log.rateHz()) else "VESC DÉCONNECTÉ", if (linked) C.OK else C.BAD)
        val st = if (!e.running) "STOPPED" else if (e.paused) "PAUSE" else "RUNNING"
        setChip(simChip, "SIM $st · ${e.t.toInt()} s", if (st == "RUNNING") C.OK else if (st == "PAUSE") C.WARN else C.BAD)
        setChip(bleChip, if (s.bleOn) (if (s.ble?.isConnected == true) "BLE ●" else "BLE ◌") else "BLE ○", if (s.bleOn) C.CYAN else C.MUTED)
        for (p in pages) p.update(t)
    }

    private fun setChip(c: TextView, text: String, color: Int) {
        c.text = text; c.setTextColor(color)
        c.background = GradientDrawable().apply { setColor(C.PANEL2); cornerRadius = dpf(20f); setStroke(dp(1), color) }
    }
}
