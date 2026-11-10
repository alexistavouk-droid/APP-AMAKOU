package com.vescsim.app

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.SweepGradient
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.sin

object C {
    val BG = Color.parseColor("#0b0f14"); val PANEL = Color.parseColor("#131a23"); val PANEL2 = Color.parseColor("#1b2431")
    val STROKE = Color.parseColor("#263243"); val TEXT = Color.parseColor("#e6edf3"); val MUTED = Color.parseColor("#7d8a9a")
    val CYAN = Color.parseColor("#22d3ee"); val VIOLET = Color.parseColor("#8b5cf6"); val OK = Color.parseColor("#34d399")
    val WARN = Color.parseColor("#fbbf24"); val BAD = Color.parseColor("#f87171"); val PINK = Color.parseColor("#f472b6")
    val SERIES = intArrayOf(CYAN, WARN, OK, PINK, VIOLET)
}

fun Context.dp(v: Int) = (v * resources.displayMetrics.density).toInt()
fun Context.dpf(v: Float) = v * resources.displayMetrics.density

fun Context.cardBg(color: Int = C.PANEL, radius: Int = 16, stroke: Int = C.STROKE): GradientDrawable =
    (if (color == C.PANEL) GradientDrawable(GradientDrawable.Orientation.TL_BR, intArrayOf(Color.parseColor("#182230"), Color.parseColor("#0f151d")))
    else GradientDrawable().apply { setColor(color) }).apply { cornerRadius = dpf(radius.toFloat()); setStroke(dp(1), stroke) }

fun Context.label(s: String, size: Float = 13f, color: Int = C.TEXT, bold: Boolean = false, mono: Boolean = false) = TextView(this).apply {
    text = s; textSize = size; setTextColor(color)
    typeface = if (mono) Typeface.MONOSPACE else if (bold) Typeface.create("sans-serif-medium", Typeface.BOLD) else Typeface.SANS_SERIF
}

fun Context.chip(s: String, color: Int = C.CYAN, onClick: (() -> Unit)? = null) = TextView(this).apply {
    text = s; textSize = 12f; setTextColor(color); gravity = Gravity.CENTER; typeface = Typeface.create("sans-serif-medium", Typeface.BOLD)
    setPadding(dp(12), dp(7), dp(12), dp(7))
    background = cardBg(C.PANEL2, 20, color)
    if (onClick != null) setOnClickListener { onClick() }
}

fun Context.vbox(pad: Int = 0) = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(pad), dp(pad), dp(pad), dp(pad)) }
fun Context.hbox() = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }

fun LinearLayout.addW(v: View, w: Float = 1f, margin: Int = 0): View {
    val lp = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, w)
    lp.setMargins(margin, margin, margin, margin); addView(v, lp); return v
}

/** Jauge circulaire animée (arc dégradé, graduations, valeur centrale). */
class GaugeView(ctx: Context, private val title: String, private val unit: String, private var minV: Double, private var maxV: Double,
                private val big: Boolean, private val decimals: Int = 0, private val c1: Int = C.CYAN, private val c2: Int = C.VIOLET) : View(ctx) {
    private var target = 0.0
    private var shown = 0.0
    private val bg = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; color = C.PANEL2 }
    private val fg = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND }
    private val glow = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND }
    private val dot = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE }
    private val tick = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = C.STROKE; strokeWidth = ctx.dpf(1.5f) }
    private val tx = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER; typeface = Typeface.create("sans-serif-condensed", Typeface.BOLD) }

    fun setRange(lo: Double, hi: Double) { minV = lo; maxV = hi }
    fun set(v: Double) {
        target = v
        if (v > maxV) maxV = Math.ceil(v / 10.0) * 10.0 * 1.0
        invalidate()
    }

    override fun onMeasure(w: Int, h: Int) {
        val width = MeasureSpec.getSize(w)
        setMeasuredDimension(width, if (big) (width * 0.85f).toInt() else (width * 0.9f).toInt())
    }

    override fun onDraw(c: Canvas) {
        shown += (target - shown) * 0.2
        val w = width.toFloat(); val h = height.toFloat()
        val sw = w * (if (big) 0.075f else 0.09f)
        val r = RectF(sw, sw, w - sw, w - sw)
        val cx = w / 2; val cy = w / 2; val rad = (w - 2 * sw) / 2
        bg.strokeWidth = sw; fg.strokeWidth = sw
        c.drawArc(r, 135f, 270f, false, bg)
        val frac = ((shown - minV) / (maxV - minV)).coerceIn(0.0, 1.0).toFloat()
        val col2 = if (shown < 0) C.OK else c2
        fg.shader = SweepGradient(cx, cy, intArrayOf(if (shown < 0) C.OK else c1, col2, col2), floatArrayOf(0f, 0.75f, 1f)).also {
            it.setLocalMatrix(Matrix().apply { postRotate(135f, cx, cy) })
        }
        if (frac > 0.002f) {
            glow.shader = fg.shader; glow.strokeWidth = sw * 1.8f; glow.alpha = 50
            c.drawArc(r, 135f, 270f * frac, false, glow)
            c.drawArc(r, 135f, 270f * frac, false, fg)
            val ta = Math.toRadians(135.0 + 270.0 * frac)
            c.drawCircle(cx + (rad * cos(ta)).toFloat(), cy + (rad * sin(ta)).toFloat(), sw * 0.38f, dot)
        }
        // graduations
        val n = if (big) 20 else 10
        for (i in 0..n) {
            val a = Math.toRadians(135.0 + 270.0 * i / n)
            val r1 = rad - sw * 0.9f; val r2 = rad - sw * (if (i % 5 == 0) 1.9f else 1.5f)
            c.drawLine(cx + (r1 * cos(a)).toFloat(), cy + (r1 * sin(a)).toFloat(), cx + (r2 * cos(a)).toFloat(), cy + (r2 * sin(a)).toFloat(), tick)
        }
        tx.color = C.TEXT; tx.textSize = w * (if (big) 0.24f else 0.20f)
        c.drawText(if (decimals == 0) "%.0f".format(shown) else "%.${decimals}f".format(shown), cx, cy + w * (if (big) 0.06f else 0.05f), tx)
        tx.color = C.CYAN; tx.textSize = w * (if (big) 0.075f else 0.09f)
        c.drawText(unit, cx, cy + w * (if (big) 0.17f else 0.17f), tx)
        tx.color = C.MUTED; tx.textSize = w * (if (big) 0.06f else 0.085f)
        c.drawText(title.uppercase(), cx, cy - w * (if (big) 0.19f else 0.17f), tx)
        tx.textSize = w * 0.06f
        c.drawText("%.0f".format(minV), w * 0.17f, h * (if (big) 0.82f else 0.92f), tx)
        c.drawText("%.0f".format(maxV), w * 0.83f, h * (if (big) 0.82f else 0.92f), tx)
        if (abs(target - shown) > 0.01 * (maxV - minV).coerceAtLeast(1.0)) postInvalidateOnAnimation() else shown = target
    }
}

/** Barre de batterie dégradée. */
class BatteryView(ctx: Context) : View(ctx) {
    var soc = 100.0; var volts = 0.0
    private val p = Paint(Paint.ANTI_ALIAS_FLAG)
    private val t = Paint(Paint.ANTI_ALIAS_FLAG).apply { typeface = Typeface.create("sans-serif-condensed", Typeface.BOLD); textAlign = Paint.Align.CENTER }
    fun set(s: Double, v: Double) { soc = s; volts = v; invalidate() }
    override fun onMeasure(w: Int, h: Int) = setMeasuredDimension(MeasureSpec.getSize(w), context.dp(54))
    override fun onDraw(c: Canvas) {
        val w = width.toFloat(); val h = height.toFloat(); val rd = h / 2.4f
        p.style = Paint.Style.FILL; p.shader = null; p.color = C.PANEL2
        c.drawRoundRect(RectF(0f, 0f, w - 14f, h), rd, rd, p)
        c.drawRoundRect(RectF(w - 14f, h * 0.3f, w, h * 0.7f), 4f, 4f, p)
        val frac = (soc / 100.0).coerceIn(0.0, 1.0).toFloat()
        val col = if (soc <= 10) C.BAD else if (soc <= 20) C.WARN else C.OK
        p.shader = LinearGradient(0f, 0f, w, 0f, col, if (soc <= 20) col else C.CYAN, Shader.TileMode.CLAMP)
        val fw = (w - 14f - 8f) * frac
        if (fw > 2f) c.drawRoundRect(RectF(4f, 4f, 4f + fw, h - 4f), rd - 3, rd - 3, p)
        p.shader = null
        t.color = Color.WHITE; t.textSize = h * 0.46f
        c.drawText("%.0f %%   ·   %.1f V".format(soc, volts), (w - 14f) / 2, h * 0.66f, t)
    }
}

/** Graphique temps réel multi-séries. */
class ChartView(ctx: Context, private val title: String, private val unit: String, private val names: List<String>, private val cap: Int = 240) : View(ctx) {
    private val data = names.map { ArrayDeque<Float>() }
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = ctx.dpf(2f); strokeJoin = Paint.Join.ROUND }
    private val grid = Paint().apply { color = C.STROKE; strokeWidth = 1f }
    private val tx = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = C.MUTED; textSize = ctx.dpf(10f) }
    private val bgp = Paint(Paint.ANTI_ALIAS_FLAG)
    private val fillP = Paint(Paint.ANTI_ALIAS_FLAG)

    fun add(vararg v: Double) {
        for (i in data.indices) { data[i].addLast(v[i].toFloat()); while (data[i].size > cap) data[i].removeFirst() }
        invalidate()
    }
    fun clear() { data.forEach { it.clear() }; invalidate() }

    override fun onMeasure(w: Int, h: Int) = setMeasuredDimension(MeasureSpec.getSize(w), context.dp(150))

    override fun onDraw(c: Canvas) {
        val w = width.toFloat(); val h = height.toFloat()
        bgp.color = C.PANEL; c.drawRoundRect(RectF(0f, 0f, w, h), context.dpf(16f), context.dpf(16f), bgp)
        tx.color = C.MUTED; c.drawText("$title ($unit)", context.dpf(12f), context.dpf(18f), tx)
        val l = context.dpf(38f); val r = w - context.dpf(10f); val tp = context.dpf(28f); val b = h - context.dpf(10f)
        val all = data.flatMap { it }
        if (all.size < 2) return
        var lo = all.min(); var hi = all.max()
        if (hi - lo < 1e-3f) { lo -= 1f; hi += 1f }
        val pad = (hi - lo) * 0.1f; lo -= pad; hi += pad
        for (i in 0..3) {
            val y = tp + (b - tp) * i / 3
            c.drawLine(l, y, r, y, grid)
            c.drawText("%.0f".format(hi - (hi - lo) * i / 3), 4f, y + 4f, tx)
        }
        for ((si, d) in data.withIndex()) {
            if (d.size < 2) continue
            val path = Path()
            d.forEachIndexed { i, v ->
                val x = l + (r - l) * i / (cap - 1)
                val y = b - (b - tp) * (v - lo) / (hi - lo)
                if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
            }
            line.color = C.SERIES[si % C.SERIES.size]
            if (data.size == 1) {
                val fill = Path(path)
                fill.lineTo(l + (r - l) * (d.size - 1) / (cap - 1), b); fill.lineTo(l, b); fill.close()
                fillP.shader = LinearGradient(0f, tp, 0f, b, (line.color and 0x00FFFFFF) or 0x55000000, 0, Shader.TileMode.CLAMP)
                c.drawPath(fill, fillP)
            }
            c.drawPath(path, line)
            if (names.size > 1) { tx.color = line.color; c.drawText("● ${names[si]}", w - context.dpf(80f), context.dpf(18f) + si * context.dpf(12f), tx) }
        }
    }
}

/** Tuile de mesure cliquable. */
class TileView(ctx: Context, title: String, private val unit: String) : LinearLayout(ctx) {
    private val value = ctx.label("—", 22f, C.TEXT, true)
    init {
        orientation = VERTICAL; setPadding(ctx.dp(12), ctx.dp(10), ctx.dp(12), ctx.dp(10)); background = ctx.cardBg()
        addView(ctx.label(title.uppercase(), 10f, C.MUTED, true))
        val row = ctx.hbox(); row.addView(value); row.addView(ctx.label(" $unit", 12f, C.CYAN)); addView(row)
    }
    fun set(s: String, color: Int = C.TEXT, forced: Boolean = false) {
        value.text = s; value.setTextColor(color)
        background = context.cardBg(C.PANEL, 16, if (forced) C.WARN else C.STROKE)
    }
}

/** Pédale tactile : maintenir et glisser vers le haut pour doser ; relâcher = 0. */
class PedalView(ctx: Context, private val title: String, private val color: Int, private val onValue: (Double) -> Unit) : View(ctx) {
    private var v = 0.0
    private val p = Paint(Paint.ANTI_ALIAS_FLAG)
    private val t = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER; typeface = Typeface.create("sans-serif-condensed", Typeface.BOLD) }

    override fun onMeasure(w: Int, h: Int) = setMeasuredDimension(MeasureSpec.getSize(w), context.dp(120))

    override fun onTouchEvent(e: android.view.MotionEvent): Boolean {
        when (e.actionMasked) {
            android.view.MotionEvent.ACTION_DOWN, android.view.MotionEvent.ACTION_MOVE -> {
                parent?.requestDisallowInterceptTouchEvent(true)
                v = (1.0 - e.y / height + 0.15).coerceIn(0.0, 1.0)
            }
            else -> v = 0.0
        }
        onValue(v); invalidate()
        return true
    }

    override fun onDraw(c: Canvas) {
        val w = width.toFloat(); val h = height.toFloat(); val rd = context.dpf(16f)
        p.shader = null; p.style = Paint.Style.FILL; p.color = C.PANEL2
        c.drawRoundRect(RectF(0f, 0f, w, h), rd, rd, p)
        if (v > 0) {
            val top = h * (1 - v.toFloat())
            p.shader = LinearGradient(0f, top, 0f, h, color, (color and 0x00FFFFFF) or 0x33000000, Shader.TileMode.CLAMP)
            c.save(); c.clipRect(0f, top, w, h); c.drawRoundRect(RectF(0f, 0f, w, h), rd, rd, p); c.restore()
        }
        p.shader = null; p.style = Paint.Style.STROKE; p.strokeWidth = context.dpf(1.5f); p.color = color
        c.drawRoundRect(RectF(1f, 1f, w - 1f, h - 1f), rd, rd, p)
        t.color = Color.WHITE; t.textSize = h * 0.2f
        c.drawText(title, w / 2, h * 0.45f, t)
        t.color = if (v > 0) Color.WHITE else C.MUTED; t.textSize = h * 0.16f
        c.drawText(if (v > 0) "%.0f %%".format(v * 100) else "maintenir", w / 2, h * 0.72f, t)
    }
}
