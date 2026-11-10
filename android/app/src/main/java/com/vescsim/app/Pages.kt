package com.vescsim.app

import android.app.AlertDialog
import android.graphics.Color
import android.graphics.Typeface
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.view.Gravity
import android.view.View
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.Spinner
import android.widget.Switch
import android.widget.TextView
import android.widget.AdapterView
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class ParamDef(val key: String, val label: String, val unit: String, val lo: Double, val hi: Double, val dec: Int,
               val mult: Double = 1.0, val get: (Telemetry) -> Double)

val PARAMS = listOf(
    ParamDef("rpm", "RPM moteur", "tr/min", 0.0, 2000.0, 0) { it.rpmMech },
    ParamDef("speed", "Vitesse", "km/h", 0.0, 120.0, 1) { it.speedKmh },
    ParamDef("v_in", "Tension batterie", "V", 0.0, 130.0, 1) { it.vIn },
    ParamDef("i_batt", "Courant batterie", "A", -60.0, 150.0, 1) { it.iBatt },
    ParamDef("i_motor", "Courant moteur", "A", -100.0, 200.0, 1) { it.iMotor },
    ParamDef("duty", "Rapport cyclique", "%", 0.0, 100.0, 1, 100.0) { it.duty },
    ParamDef("power_w", "Puissance", "W", -3000.0, 9000.0, 0) { it.powerW },
    ParamDef("temp_motor", "Température moteur", "°C", -20.0, 200.0, 1) { it.tempMotor },
    ParamDef("temp_fet", "Température MOSFET", "°C", -20.0, 160.0, 1) { it.tempFet },
    ParamDef("soc_pct", "Niveau batterie", "%", 0.0, 100.0, 1) { it.socPct },
    ParamDef("wh_per_km", "Consommation", "Wh/km", 0.0, 400.0, 1) { it.whPerKm },
    ParamDef("distance_km", "Distance parcourue", "km", 0.0, 9999.0, 3) { it.distanceKm },
    ParamDef("wh_used", "Wh consommés", "Wh", 0.0, 9999.0, 2) { it.whUsed },
    ParamDef("wh_regen", "Wh récupérés", "Wh", 0.0, 9999.0, 2) { it.whRegen }
)

fun paramOf(key: String) = PARAMS.first { it.key == key }

abstract class Page(val s: AppState) {
    abstract val view: View
    var visible = false
    abstract fun update(t: Telemetry)
}

fun showEdit(s: AppState, d: ParamDef, t: Telemetry) {
    val act = s.act
    val et = EditText(act).apply {
        inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL or InputType.TYPE_NUMBER_FLAG_SIGNED
        setText("%.${d.dec}f".format(Locale.US, (s.engine.forcedValue(d.key)?.times(d.mult)) ?: (d.get(t) * d.mult)))
        setSelectAllOnFocus(true); setTextColor(C.TEXT)
    }
    AlertDialog.Builder(act, AlertDialog.THEME_DEVICE_DEFAULT_DARK)
        .setTitle("${d.label} (${d.unit})")
        .setMessage("Valeur envoyée à l'écran, tant qu'elle est forcée.")
        .setView(et)
        .setPositiveButton("Forcer") { _, _ ->
            et.text.toString().replace(',', '.').toDoubleOrNull()?.let { s.engine.setOverride(d.key, it / d.mult) }
        }
        .setNeutralButton("Libérer") { _, _ -> s.engine.clearOverride(d.key) }
        .setNegativeButton("Annuler", null).show()
}

// ============================================================================ TABLEAU DE BORD
class DashboardPage(s: AppState) : Page(s) {
    private val a = s.act
    private val speedG = GaugeView(a, "Vitesse", "km/h", 0.0, 60.0, true)
    private val powerG = GaugeView(a, "Puissance", "W", -500.0, 2000.0, false, 0, C.WARN, C.PINK)
    private val rpmG = GaugeView(a, "RPM moteur", "tr/min", 0.0, 1000.0, false, 0, C.VIOLET, C.CYAN)
    private val batt = BatteryView(a)
    private val banner = a.label("", 14f, Color.WHITE, true).apply { gravity = Gravity.CENTER; setPadding(a.dp(10), a.dp(10), a.dp(10), a.dp(10)); background = a.cardBg(C.BAD, 14, C.BAD); visibility = View.GONE }
    private val info = a.label("", 11f, C.MUTED)
    private val tiles = LinkedHashMap<String, TileView>()
    private val charts = listOf(ChartView(a, "Vitesse", "km/h", listOf("v")), ChartView(a, "Puissance", "W", listOf("P")),
        ChartView(a, "Tension batterie", "V", listOf("V")), ChartView(a, "Intensité", "A", listOf("batterie", "moteur")),
        ChartView(a, "Températures", "°C", listOf("moteur", "MOSFET")), ChartView(a, "RPM moteur", "tr/min", listOf("rpm")))
    private val modeChips = ArrayList<TextView>()

    private val tileDefs = listOf(
        Triple("v_in", "Tension", "%.1f"), Triple("i_batt", "Courant batt.", "%+.1f"), Triple("i_motor", "Courant moteur", "%+.1f"),
        Triple("power_w", "Puissance", "%+.0f"), Triple("temp_fet", "MOSFET", "%.1f"), Triple("temp_motor", "Moteur", "%.1f"),
        Triple("wh_per_km", "Consommation", "%.1f"), Triple("distance_km", "Distance", "%.3f"), Triple("wh_used", "Wh consommés", "%.2f"),
        Triple("rpm", "RPM moteur", "%.0f"), Triple("duty", "Rapport cyclique", "%.0f"), Triple("soc_pct", "Batterie", "%.1f")
    )

    override val view: View = ScrollView(a).apply {
        val col = a.vbox(12)
        addView(col)
        col.addView(banner); col.addView(speedG)
        val g2 = a.hbox(); g2.addW(powerG, 1f, a.dp(4)); g2.addW(rpmG, 1f, a.dp(4)); col.addView(g2)
        col.addView(batt)
        col.addView(info.also { it.setPadding(0, a.dp(6), 0, a.dp(6)) })
        // commandes
        val ctl = a.hbox()
        ctl.addW(a.chip("▶ START", C.OK) { s.engine.running = true; s.engine.paused = false }, 1f, a.dp(3))
        ctl.addW(a.chip("⏸ PAUSE", C.WARN) { s.engine.paused = !s.engine.paused }, 1f, a.dp(3))
        ctl.addW(a.chip("■ STOP", C.BAD) { s.engine.running = false; s.engine.throttle = 0.0 }, 1f, a.dp(3))
        ctl.addW(a.chip("↺ RESET", C.CYAN) { s.engine.setScenario(null); s.engine.reset(); s.engine.running = true; charts.forEach { it.clear() } }, 1f, a.dp(3))
        col.addView(ctl)
        val modes = a.hbox().also { it.setPadding(0, a.dp(6), 0, a.dp(6)) }
        for ((n, v) in listOf("Ralenti ×0,25" to 0.25, "Normal ×1" to 1.0, "Accéléré ×4" to 4.0)) {
            val ch = a.chip(n, C.VIOLET) { s.engine.timeScale = v }
            modeChips.add(ch); modes.addW(ch, 1f, a.dp(3))
        }
        col.addView(modes)
        col.addView(a.label("MESURES — touchez une valeur pour la modifier", 11f, C.MUTED, true).also { it.setPadding(0, a.dp(8), 0, a.dp(4)) })
        for (i in tileDefs.indices step 2) {
            val row = a.hbox()
            for (j in i until minOf(i + 2, tileDefs.size)) {
                val (key, title, _) = tileDefs[j]
                val def = paramOf(key)
                val tv = TileView(a, title, def.unit)
                tv.setOnClickListener { showEdit(s, def, s.engine.snapshot()) }
                tiles[key] = tv; row.addW(tv, 1f, a.dp(4))
            }
            col.addView(row)
        }
        col.addView(a.label("GRAPHIQUES", 11f, C.MUTED, true).also { it.setPadding(0, a.dp(14), 0, a.dp(4)) })
        for (c in charts) { col.addView(c); (c.layoutParams as LinearLayout.LayoutParams).bottomMargin = a.dp(8) }
    }

    override fun update(t: Telemetry) {
        speedG.set(t.speedKmh); powerG.set(t.powerW); rpmG.set(t.rpmMech)
        batt.set(t.socPct, t.vIn)
        if (t.fault != 0) { banner.text = "⚠ DÉFAUT CONTRÔLEUR : ${Vesc.FAULT_NAMES[t.fault] ?: t.fault} (code ${t.fault})"; banner.visibility = View.VISIBLE }
        else banner.visibility = View.GONE
        info.text = "État thermique ${t.thermalState} · limitation ${"%.0f".format(t.powerLimitPct)} % · couple ${"%.1f".format(t.torqueNm)} N·m · ERPM envoyé ${"%.0f".format(t.erpm)}"
        for ((key, tv) in tiles) {
            val d = paramOf(key); val v = d.get(t) * d.mult
            val f = tileDefs.first { it.first == key }.third
            val col = when {
                (key == "temp_fet" || key == "temp_motor") && v >= 100 -> C.BAD
                (key == "temp_fet" || key == "temp_motor") && v >= 80 -> C.WARN
                key == "soc_pct" && v <= 10 -> C.BAD
                key == "soc_pct" && v <= 20 -> C.WARN
                (key == "i_batt" || key == "power_w") && v < -0.5 -> C.OK
                else -> C.TEXT
            }
            tv.set(f.format(Locale.US, v), col, s.engine.forced(key) || (key == "rpm" && s.engine.forced("speed")))
        }
        charts[0].add(t.speedKmh); charts[1].add(t.powerW); charts[2].add(t.vIn); charts[3].add(t.iBatt, t.iMotor)
        charts[4].add(t.tempMotor, t.tempFet); charts[5].add(t.rpmMech)
        val ts = s.engine.timeScale
        val sel = if (ts < 0.5) 0 else if (ts < 2) 1 else 2
        modeChips.forEachIndexed { i, c -> c.alpha = if (i == sel) 1f else 0.45f }
    }
}

// ============================================================================ CONTRÔLE (toutes les valeurs)
class ParamRow(private val s: AppState, private val d: ParamDef) : LinearLayout(s.act) {
    private val valueBtn = context.chip("—", C.CYAN)
    private val sw = Switch(context)
    private val sb = SeekBar(context).apply { max = 1000 }
    private var internal = false

    init {
        orientation = VERTICAL; setPadding(context.dp(12), context.dp(8), context.dp(12), context.dp(6)); background = context.cardBg()
        val top = context.hbox()
        top.addW(context.label(d.label, 14f, C.TEXT, true), 1f)
        top.addView(valueBtn); top.addView(sw)
        addView(top); addView(sb)
        valueBtn.setOnClickListener { showEdit(s, d, s.engine.snapshot()) }
        sb.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(x: SeekBar?, p: Int, fromUser: Boolean) {
                if (!fromUser || internal) return
                s.engine.setOverride(d.key, (d.lo + (d.hi - d.lo) * p / 1000.0) / d.mult)
            }
            override fun onStartTrackingTouch(x: SeekBar?) {}
            override fun onStopTrackingTouch(x: SeekBar?) {}
        })
        sw.setOnCheckedChangeListener { _, on -> if (!internal && !on) s.engine.clearOverride(d.key) }
        sw.setOnClickListener { if (sw.isChecked) s.engine.setOverride(d.key, d.get(s.engine.snapshot())) }
    }

    fun update(t: Telemetry) {
        val forced = s.engine.forced(d.key)
        val v = if (forced) s.engine.forcedValue(d.key)!! * d.mult else d.get(t) * d.mult
        internal = true
        sw.isChecked = forced
        if (!sb.isPressed) sb.progress = (((v - d.lo) / (d.hi - d.lo)) * 1000).toInt().coerceIn(0, 1000)
        internal = false
        valueBtn.text = "%.${d.dec}f %s".format(Locale.US, v, d.unit)
        valueBtn.background = context.cardBg(C.PANEL2, 20, if (forced) C.WARN else C.CYAN)
        valueBtn.setTextColor(if (forced) C.WARN else C.CYAN)
    }
}

class ControlPage(s: AppState) : Page(s) {
    private val a = s.act
    private val rows = PARAMS.map { ParamRow(s, it) }
    private val thrLabel = a.label("Accélérateur : 0 %", 14f, C.TEXT, true)
    private val thr = SeekBar(a).apply { max = 200; progress = 100 }
    private val faultBtns = ArrayList<Pair<TextView, () -> Boolean>>()

    override val view: View = ScrollView(a).apply {
        val col = a.vbox(12); addView(col)
        col.addView(a.label("Toutes les valeurs sont modifiables. Curseur ou touche sur la valeur pour saisir ; l'interrupteur force / libère la valeur envoyée à l'écran.", 12f, C.MUTED))
        val hdr = a.hbox().also { it.setPadding(0, a.dp(8), 0, a.dp(8)) }
        hdr.addW(a.chip("Tout libérer", C.WARN) { s.engine.clearOverride(null); s.engine.faultCode = 0; s.engine.link.up = true; s.engine.link.dropRate = 0.0; s.engine.link.crcCorruptRate = 0.0 }, 1f, a.dp(3))
        hdr.addW(a.chip("Vecteur de référence", C.CYAN) { s.engine.applyReferenceVector() }, 1f, a.dp(3))
        col.addView(hdr)

        val box = a.vbox(12).also { it.background = a.cardBg() }
        box.addView(thrLabel); box.addView(thr)
        thr.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(x: SeekBar?, p: Int, u: Boolean) { thrLabel.text = "Accélérateur : ${p - 100} %  (négatif = frein régénératif)"; if (u) s.engine.throttle = (p - 100) / 100.0 }
            override fun onStartTrackingTouch(x: SeekBar?) {}
            override fun onStopTrackingTouch(x: SeekBar?) {}
        })
        col.addView(box)
        col.addView(a.label("VALEURS", 11f, C.MUTED, true).also { it.setPadding(0, a.dp(12), 0, a.dp(4)) })
        for (r in rows) { col.addView(r); (r.layoutParams as LinearLayout.LayoutParams).bottomMargin = a.dp(6) }

        col.addView(a.label("DÉFAUTS ET LIAISON", 11f, C.MUTED, true).also { it.setPadding(0, a.dp(12), 0, a.dp(4)) })
        val items = listOf<Triple<String, () -> Unit, () -> Boolean>>(
            Triple("Aucun défaut", { s.engine.faultCode = 0 }, { s.engine.faultCode == 0 }),
            Triple("Surtension", { s.engine.faultCode = Vesc.FAULT_OVER_VOLTAGE }, { s.engine.faultCode == 1 }),
            Triple("Sous-tension", { s.engine.faultCode = Vesc.FAULT_UNDER_VOLTAGE }, { s.engine.faultCode == 2 }),
            Triple("Surchauffe FET", { s.engine.faultCode = Vesc.FAULT_OVER_TEMP_FET }, { s.engine.faultCode == 5 }),
            Triple("Surchauffe moteur", { s.engine.faultCode = Vesc.FAULT_OVER_TEMP_MOTOR }, { s.engine.faultCode == 6 }),
            Triple("Surintensité", { s.engine.faultCode = Vesc.FAULT_ABS_OVER_CURRENT }, { s.engine.faultCode == 4 }),
            Triple("Erreur moteur", { s.engine.faultCode = Vesc.FAULT_UNBALANCED_CURRENTS }, { s.engine.faultCode == 17 }),
            Triple("Liaison coupée", { s.engine.link.up = !s.engine.link.up }, { !s.engine.link.up }),
            Triple("Pertes 50 %", { s.engine.link.dropRate = if (s.engine.link.dropRate > 0) 0.0 else 0.5 }, { s.engine.link.dropRate > 0 }),
            Triple("CRC corrompu", { s.engine.link.crcCorruptRate = if (s.engine.link.crcCorruptRate > 0) 0.0 else 0.4 }, { s.engine.link.crcCorruptRate > 0 })
        )
        for (i in items.indices step 2) {
            val row = a.hbox()
            for (j in i until minOf(i + 2, items.size)) {
                val (n, act, on) = items[j]
                val ch = a.chip(n, C.BAD) { act() }
                faultBtns.add(ch to on); row.addW(ch, 1f, a.dp(3))
            }
            col.addView(row)
        }
    }

    override fun update(t: Telemetry) {
        rows.forEach { it.update(t) }
        for ((c, on) in faultBtns) { c.alpha = if (on()) 1f else 0.5f; c.background = a.cardBg(if (on()) C.PANEL2 else C.PANEL, 20, C.BAD) }
    }
}

// ============================================================================ RÉGLAGES
class SettingsPage(s: AppState) : Page(s) {
    private val a = s.act
    private val fields = LinkedHashMap<String, EditText>()
    private val msg = a.label("", 12f, C.OK)
    private val profSpin = Spinner(a)
    private val profName = EditText(a).apply { hint = "Nom du profil"; setTextColor(C.TEXT); setHintTextColor(C.MUTED); setSingleLine() }

    private fun field(col: LinearLayout, key: String, label: String, numeric: Boolean = true) {
        val et = EditText(a).apply {
            setTextColor(C.TEXT); setSingleLine(); gravity = Gravity.END
            inputType = if (numeric) InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL else InputType.TYPE_CLASS_TEXT
        }
        fields[key] = et
        val row = a.hbox(); row.addW(a.label(label, 13f, C.MUTED), 1.2f); row.addW(et, 1f); col.addView(row)
    }

    private fun refreshProfiles() {
        val names = s.profiles().keys().asSequence().toList().sorted()
        profSpin.adapter = ArrayAdapter(a, android.R.layout.simple_spinner_dropdown_item, names)
    }

    fun fill() {
        val j = s.toJson()
        for ((k, et) in fields) {
            if (!et.hasFocus()) et.setText(if (j.get(k) is Double) "%.3f".format(Locale.US, j.getDouble(k)).trimEnd('0').trimEnd('.') else j.get(k).toString())
        }
    }

    private fun apply() {
        try {
            val j = s.toJson()
            for ((k, et) in fields) {
                val v = et.text.toString().replace(',', '.')
                when (j.get(k)) {
                    is String -> j.put(k, v)
                    is Int -> j.put(k, v.toDouble().toInt())
                    else -> j.put(k, v.toDouble())
                }
            }
            if (!(j.getDouble("min") < j.getDouble("nominal") && j.getDouble("nominal") < j.getDouble("max"))) { msg.setTextColor(C.BAD); msg.text = "Il faut Vmin < Vnominale < Vmax"; return }
            s.applyJson(j); s.saveLast(); msg.setTextColor(C.OK); msg.text = "Configuration appliquée ✔"
        } catch (e: Exception) { msg.setTextColor(C.BAD); msg.text = "Valeur invalide : ${e.message}" }
    }

    override val view: View = ScrollView(a).apply {
        val col = a.vbox(12); addView(col)
        col.addView(a.label("PROFILS DE BATTERIE", 11f, C.MUTED, true))
        val presets = a.hbox().also { it.setPadding(0, a.dp(6), 0, a.dp(6)) }
        for (p in PRESETS) presets.addW(a.chip(p.name.replace(" ", ""), C.CYAN) {
            fields["nominal"]?.setText(p.nominal.toString()); fields["max"]?.setText(p.max.toString()); fields["min"]?.setText(p.min.toString())
            fields["ah"]?.setText(p.ah.toString()); fields["maxMotorA"]?.setText(p.maxMotorA.toString()); fields["maxBattA"]?.setText(p.maxBattA.toString())
            fields["kt"]?.setText(p.kt.toString()); fields["wheelM"]?.setText(p.wheelM.toString()); fields["massKg"]?.setText(p.massKg.toString())
            msg.setTextColor(C.WARN); msg.text = "Profil ${p.name} chargé dans les champs — appuyez sur Appliquer"
        }, 1f, a.dp(2))
        col.addView(presets)
        val b = a.vbox(12).also { it.background = a.cardBg() }
        b.addView(a.label("Batterie", 14f, C.CYAN, true))
        field(b, "nominal", "Tension nominale (V)"); field(b, "max", "Tension max (V)"); field(b, "min", "Tension min (V)")
        field(b, "ah", "Capacité (Ah)"); field(b, "initSoc", "Charge initiale (%)"); field(b, "rIntMohm", "Résistance interne (mΩ)")
        col.addView(b); (b.layoutParams as LinearLayout.LayoutParams).bottomMargin = a.dp(8)
        val m = a.vbox(12).also { it.background = a.cardBg() }
        m.addView(a.label("Moteur et véhicule", 14f, C.CYAN, true))
        field(m, "poles", "Nombre de pôles"); field(m, "kt", "Constante de couple (N·m/A)"); field(m, "wheelM", "Diamètre de roue (m)")
        field(m, "massKg", "Masse totale (kg)")
        col.addView(m); (m.layoutParams as LinearLayout.LayoutParams).bottomMargin = a.dp(8)
        val c = a.vbox(12).also { it.background = a.cardBg() }
        c.addView(a.label("Contrôleur", 14f, C.CYAN, true))
        field(c, "maxMotorA", "Courant moteur max (A)"); field(c, "maxBattA", "Courant batterie max (A)"); field(c, "regenA", "Courant régén. max (A, 0 = auto)")
        field(c, "controllerId", "ID contrôleur / CAN"); field(c, "fwMajor", "Firmware majeur"); field(c, "fwMinor", "Firmware mineur")
        field(c, "hwName", "Nom matériel", false); field(c, "bleName", "Nom Bluetooth annoncé", false)
        col.addView(c); (c.layoutParams as LinearLayout.LayoutParams).bottomMargin = a.dp(8)
        col.addView(a.chip("✔ APPLIQUER LA CONFIGURATION", C.OK) { apply() })
        col.addView(msg)
        col.addView(a.label("PROFILS PERSONNALISÉS", 11f, C.MUTED, true).also { it.setPadding(0, a.dp(14), 0, a.dp(4)) })
        val pb = a.vbox(12).also { it.background = a.cardBg() }
        pb.addView(profSpin)
        val r1 = a.hbox()
        r1.addW(a.chip("Charger", C.CYAN) { (profSpin.selectedItem as? String)?.let { n -> s.loadProfile(n); fill(); msg.setTextColor(C.OK); msg.text = "Profil « $n » chargé" } }, 1f, a.dp(3))
        r1.addW(a.chip("Supprimer", C.BAD) { (profSpin.selectedItem as? String)?.let { n -> s.deleteProfile(n); refreshProfiles() } }, 1f, a.dp(3))
        pb.addView(r1)
        pb.addView(profName)
        pb.addView(a.chip("Enregistrer la configuration actuelle", C.OK) {
            val n = profName.text.toString().trim()
            if (n.isNotEmpty()) { apply(); s.saveProfile(n); refreshProfiles(); msg.setTextColor(C.OK); msg.text = "Profil « $n » enregistré" }
        })
        col.addView(pb)
        refreshProfiles(); fill()
    }

    override fun update(t: Telemetry) { if (visible && fields["nominal"]?.hasFocus() != true) { /* ne pas écraser la saisie */ } }
    fun onShow() = fill()
}

// ============================================================================ SCÉNARIOS
class ScenarioPage(s: AppState) : Page(s) {
    private val a = s.act
    private val status = a.label("Aucun scénario actif", 13f, C.TEXT, true)
    private val bar = android.widget.ProgressBar(a, null, android.R.attr.progressBarStyleHorizontal).apply { max = 100 }

    override val view: View = ScrollView(a).apply {
        val col = a.vbox(12); addView(col)
        val top = a.vbox(12).also { it.background = a.cardBg() }
        top.addView(status); top.addView(bar)
        top.addView(a.chip("■ Arrêter le scénario", C.BAD) {
            s.engine.setScenario(null); s.engine.link.up = true; s.engine.link.dropRate = 0.0; s.engine.link.crcCorruptRate = 0.0
        })
        col.addView(top); (top.layoutParams as LinearLayout.LayoutParams).bottomMargin = a.dp(10)
        for ((i, sc) in Scenarios.all().withIndex()) {
            val card = a.vbox(12).also { it.background = a.cardBg() }
            card.addView(a.label("${sc.id}. ${sc.name}", 16f, C.TEXT, true))
            card.addView(a.label(sc.description, 12f, C.MUTED))
            card.addView(a.label("Durée ≈ ${sc.duration.toInt()} s", 11f, C.CYAN).also { it.setPadding(0, a.dp(4), 0, a.dp(6)) })
            card.addView(a.chip("▶ Lancer", C.OK) { s.engine.running = true; s.engine.paused = false; s.engine.setScenario(Scenarios.all()[i]) })
            col.addView(card); (card.layoutParams as LinearLayout.LayoutParams).bottomMargin = a.dp(8)
        }
    }

    override fun update(t: Telemetry) {
        val sc = s.engine.scenario
        if (sc == null) { status.text = "Aucun scénario actif"; bar.progress = 0 }
        else { val tt = s.engine.t - sc.t0; bar.progress = (100 * (tt / sc.duration)).toInt().coerceIn(0, 100); status.text = "En cours : ${sc.name} (${tt.toInt()}/${sc.duration.toInt()} s) ${sc.current}" }
    }
}

// ============================================================================ DIAGNOSTIC + DASHBOARD TEST
class DiagPage(s: AppState) : Page(s) {
    private val a = s.act
    private val ui = Handler(Looper.getMainLooper())
    private val bleLbl = a.label("", 13f, C.TEXT, true)
    private val bleBtn = a.chip("Démarrer le Bluetooth", C.OK) { s.toggleBle() }
    private val checks = a.label("", 12f, C.TEXT, mono = true)
    private val sent = a.label("", 11f, C.TEXT, mono = true)
    private val stats = a.label("", 12f, C.MUTED)
    private val logV = a.label("", 10f, C.TEXT, mono = true)
    private var linkPhase = "idle"; private var cutAt = 0L; private var restoredAt = 0L; private var rxAtCut = 0; private var returnMs = -1L

    override val view: View = ScrollView(a).apply {
        val col = a.vbox(12); addView(col)
        val b = a.vbox(12).also { it.background = a.cardBg() }
        b.addView(a.label("BLUETOOTH (BLE · Nordic UART)", 11f, C.MUTED, true)); b.addView(bleLbl); b.addView(bleBtn)
        b.addView(a.label("Service 6E400001-B5A3-F393-E0A9-E50E24DCCA9E\nRX …0002 (écriture) · TX …0003 (notifications)", 10f, C.MUTED, mono = true))
        col.addView(b); (b.layoutParams as LinearLayout.LayoutParams).bottomMargin = a.dp(8)

        val t = a.vbox(12).also { it.background = a.cardBg() }
        t.addView(a.label("DASHBOARD TEST", 11f, C.MUTED, true)); t.addView(checks)
        val r = a.hbox().also { it.setPadding(0, a.dp(6), 0, 0) }
        r.addW(a.chip("Vecteur de référence", C.CYAN) { s.engine.applyReferenceVector() }, 1f, a.dp(3))
        r.addW(a.chip("Test déconnexion", C.WARN) { startLinkTest() }, 1f, a.dp(3))
        t.addView(r)
        t.addView(a.label("Référence : 500 tr/min, 48,0 V, 10,0 A, moteur 55 °C, MOSFET 40 °C, batterie 50 %. Comparez avec l'écran.", 11f, C.MUTED))
        col.addView(t); (t.layoutParams as LinearLayout.LayoutParams).bottomMargin = a.dp(8)

        val e = a.vbox(12).also { it.background = a.cardBg() }
        e.addView(a.label("ENVOYÉ À L'ÉCRAN (valeur → codage trame)", 11f, C.MUTED, true)); e.addView(sent)
        col.addView(e); (e.layoutParams as LinearLayout.LayoutParams).bottomMargin = a.dp(8)

        col.addView(stats)
        col.addView(a.chip("Effacer le journal", C.MUTED) { s.log.clear() })
        col.addView(logV.also { it.setPadding(a.dp(8), a.dp(8), a.dp(8), a.dp(8)); it.background = a.cardBg() })
    }

    private fun startLinkTest() {
        linkPhase = "cut"; cutAt = System.currentTimeMillis(); rxAtCut = s.log.rx; returnMs = -1; s.engine.link.up = false
        s.log.info("Test déconnexion : liaison coupée 6 s", "WARN")
        ui.postDelayed({ s.engine.link.up = true; restoredAt = System.currentTimeMillis(); linkPhase = "restored"; s.log.info("Test déconnexion : liaison rétablie") }, 6000)
    }

    private fun colored(lines: List<Pair<String, Int>>): CharSequence {
        val sb = SpannableStringBuilder()
        for ((t, c) in lines) { val st = sb.length; sb.append(t).append('\n'); sb.setSpan(ForegroundColorSpan(c), st, sb.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE) }
        return sb
    }

    override fun update(t: Telemetry) {
        bleLbl.text = "État : ${s.bleState}" + (s.ble?.clientName?.takeIf { it.isNotEmpty() && s.ble?.isConnected == true }?.let { "\nClient : $it" } ?: "")
        bleBtn.text = if (s.bleOn) "Arrêter le Bluetooth" else "Démarrer le Bluetooth"
        if (!visible) return
        val lg = s.log
        val since = if (lg.lastRxMs == 0L) -1.0 else (System.currentTimeMillis() - lg.lastRxMs) / 1000.0
        if (linkPhase == "restored" && returnMs < 0 && lg.tx > 0 && lg.lastRxMs > restoredAt) { returnMs = System.currentTimeMillis() - restoredAt; linkPhase = "done" }
        fun st(ok: Boolean?, okT: String, koT: String, wait: String) = if (ok == null) "… $wait" to C.WARN else if (ok) "✔ $okT" to C.OK else "✘ $koT" to C.BAD
        val gv = lg.count(Vesc.GET_VALUES) + lg.count(Vesc.GET_VALUES_SELECTIVE); val gs = lg.count(Vesc.GET_VALUES_SETUP) + lg.count(Vesc.GET_VALUES_SETUP_SELECTIVE)
        val rows = ArrayList<Pair<String, Int>>()
        rows += if (since < 0) "… Connexion : aucune requête reçue" to C.WARN else if (since <= 3) "✔ Connexion : dernière requête il y a %.1f s".format(since) to C.OK else "✘ Connexion perdue depuis %.0f s".format(since) to C.BAD
        rows += (if (gv > 0) "✔ RPM / tension / courants / températures / défauts : $gv requêtes" to C.OK else "… GET_VALUES jamais demandé" to C.WARN)
        rows += (if (gs > 0) "✔ Niveau batterie + vitesse (SETUP) : $gs requêtes" to C.OK else "… GET_VALUES_SETUP jamais demandé" to C.WARN)
        rows += (if (lg.crcErrors == 0) "✔ Aucune erreur CRC" to C.OK else "✘ ${lg.crcErrors} erreur(s) CRC" to C.BAD)
        rows += when (linkPhase) {
            "idle" -> "• Déconnexion / retour : lancer « Test déconnexion »" to C.MUTED
            "cut" -> "… Liaison coupée : l'écran doit afficher « déconnecté »" to C.WARN
            "restored" -> "… Liaison rétablie, attente de l'écran…" to C.WARN
            else -> "✔ Retour de connexion en %.1f s (%d requêtes sans réponse)".format(returnMs / 1000.0, lg.rx - rxAtCut) to C.OK
        }
        checks.text = colored(rows)
        val v = t.vescValues(); val sv = t.setupValues()
        sent.text = listOf(
            "RPM élec.  %8.0f → %d".format(t.erpm, v["rpm"]!!.toInt()),
            "Vitesse    %6.1f km/h → %d (×1e3 m/s)".format(t.speedKmh, (sv["speed"]!! * 1000).toInt()),
            "Tension    %6.1f V → %d (×10)".format(t.vIn, (v["v_in"]!! * 10).toInt()),
            "I batterie %+6.2f A → %d (×100)".format(t.iBatt, (v["avg_input_current"]!! * 100).toInt()),
            "I moteur   %+6.2f A → %d (×100)".format(t.iMotor, (v["avg_motor_current"]!! * 100).toInt()),
            "T MOSFET   %6.1f °C → %d (×10)".format(t.tempFet, (v["temp_fet"]!! * 10).toInt()),
            "T moteur   %6.1f °C → %d (×10)".format(t.tempMotor, (v["temp_motor"]!! * 10).toInt()),
            "Batterie   %6.1f %% → %d (×1000)".format(t.socPct, (sv["battery_level"]!! * 1000).toInt()),
            "Défaut     %d (${Vesc.FAULT_NAMES[t.fault] ?: "?"})".format(t.fault)
        ).joinToString("\n")
        stats.text = "RX ${lg.rx} · TX ${lg.tx} · CRC ${lg.crcErrors} · bloquées ${lg.blocked} · inconnues ${lg.unknown} · octets perdus ${s.responder.decoder.droppedBytes} · %.1f Hz".format(lg.rateHz())
        val fmt = SimpleDateFormat("HH:mm:ss.SSS", Locale.US)
        val sb = SpannableStringBuilder()
        for (e in lg.tail(50)) {
            val tm = fmt.format(Date(e.ts))
            val (line, col) = if (e.dir == "RX" || e.dir == "TX") {
                val h = if (e.hex.length > 44) e.hex.substring(0, 44) + "…" else e.hex
                "$tm ${e.dir} ${e.cmdName.removePrefix("COMM_")} len=${e.size} crc=%04X/%04X %s\n   %s".format(e.crcCalc ?: 0, e.crcRx ?: 0, if (e.valid == true) "OK" else "KO", h) to
                    (if (e.valid == false) C.BAD else if (e.dir == "TX") C.CYAN else C.TEXT)
            } else "$tm [${e.dir}] ${e.msg}" to (if (e.dir == "ERR") C.BAD else if (e.dir == "WARN") C.WARN else C.MUTED)
            val st = sb.length; sb.append(line).append('\n'); sb.setSpan(ForegroundColorSpan(col), st, sb.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        }
        logV.text = sb
    }
}
