package com.vescsim.app

import java.io.ByteArrayOutputStream

/**
 * Protocole VESC (framing, CRC16, charges utiles) — port Kotlin de la version Python/Windows.
 * Référence : firmware officiel vedderb/bldc (util/crc.c, comm/packet.c, comm/commands.c, datatypes.h).
 */
object Vesc {
    const val FW_VERSION = 0
    const val GET_VALUES = 4
    const val GET_MCCONF = 14
    const val GET_APPCONF = 17
    const val ALIVE = 30
    const val FORWARD_CAN = 34
    const val GET_VALUES_SETUP = 47
    const val GET_VALUES_SELECTIVE = 50
    const val GET_VALUES_SETUP_SELECTIVE = 51
    const val PING_CAN = 62
    const val GET_IMU_DATA = 65
    const val MAX_PAYLOAD = 512

    const val FAULT_OVER_VOLTAGE = 1
    const val FAULT_UNDER_VOLTAGE = 2
    const val FAULT_ABS_OVER_CURRENT = 4
    const val FAULT_OVER_TEMP_FET = 5
    const val FAULT_OVER_TEMP_MOTOR = 6
    const val FAULT_UNBALANCED_CURRENTS = 17

    val FAULT_NAMES = mapOf(
        0 to "AUCUN", 1 to "SURTENSION", 2 to "SOUS-TENSION", 3 to "DRV", 4 to "SURINTENSITE",
        5 to "SURCHAUFFE MOSFET", 6 to "SURCHAUFFE MOTEUR", 17 to "COURANTS DESEQUILIBRES"
    )

    private val NAMES = mapOf(
        0 to "FW_VERSION", 1 to "JUMP_TO_BOOTLOADER", 2 to "ERASE_NEW_APP", 3 to "WRITE_NEW_APP_DATA",
        4 to "GET_VALUES", 5 to "SET_DUTY", 6 to "SET_CURRENT", 7 to "SET_CURRENT_BRAKE", 8 to "SET_RPM",
        9 to "SET_POS", 10 to "SET_HANDBRAKE", 11 to "SET_DETECT", 12 to "SET_SERVO_POS",
        13 to "SET_MCCONF", 14 to "GET_MCCONF", 16 to "SET_APPCONF", 17 to "GET_APPCONF",
        20 to "TERMINAL_CMD", 29 to "REBOOT", 30 to "ALIVE", 34 to "FORWARD_CAN", 35 to "SET_CHUCK_DATA",
        36 to "CUSTOM_APP_DATA", 47 to "GET_VALUES_SETUP", 50 to "GET_VALUES_SELECTIVE",
        51 to "GET_VALUES_SETUP_SELECTIVE", 62 to "PING_CAN", 65 to "GET_IMU_DATA"
    )

    fun name(id: Int) = "COMM_" + (NAMES[id] ?: id.toString())

    /** Pilotage / configuration / mise à jour : toujours bloqué (télémétrie seule). */
    val BLOCKED = setOf(
        1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16, 18, 19, 20, 24, 25, 26, 27, 28, 29, 35, 36,
        38, 39, 40, 41, 42, 43, 44, 45, 46, 48, 49, 57, 58, 59, 60, 61, 63, 64
    )
    val UNSUPPORTED = setOf(GET_MCCONF, GET_APPCONF, GET_IMU_DATA, 31, 32, 33)

    // ---- CRC16 (poly 0x1021, init 0)
    private val TAB = IntArray(256) { i ->
        var c = i shl 8
        repeat(8) { c = if (c and 0x8000 != 0) ((c shl 1) xor 0x1021) and 0xFFFF else (c shl 1) and 0xFFFF }
        c
    }

    fun crc16(data: ByteArray, off: Int = 0, len: Int = data.size - off): Int {
        var c = 0
        for (i in off until off + len) {
            c = TAB[((c shr 8) xor (data[i].toInt() and 0xFF)) and 0xFF] xor ((c shl 8) and 0xFFFF)
        }
        return c
    }

    fun frame(payload: ByteArray): ByteArray {
        val n = payload.size
        require(n in 1..MAX_PAYLOAD) { "longueur invalide" }
        val o = ByteArrayOutputStream()
        if (n <= 255) { o.write(2); o.write(n) } else { o.write(3); o.write(n shr 8); o.write(n and 0xFF) }
        o.write(payload)
        val c = crc16(payload)
        o.write(c shr 8); o.write(c and 0xFF); o.write(3)
        return o.toByteArray()
    }

    fun request(cmd: Int, extra: ByteArray = ByteArray(0)): ByteArray = frame(byteArrayOf(cmd.toByte()) + extra)

    class Frame(val payload: ByteArray, val raw: ByteArray, val crcRx: Int, val crcCalc: Int, val ok: Boolean, val error: String = "") {
        val cmdId: Int get() = if (payload.isEmpty()) -1 else payload[0].toInt() and 0xFF
    }

    /** Décodeur incrémental équivalent à packet_process_byte() du firmware. */
    class Decoder(private val timeoutMs: Long = 250) {
        private var buf = ByteArray(0)
        private var last = System.nanoTime()
        var droppedBytes = 0

        fun reset() { buf = ByteArray(0) }

        private fun drop(n: Int) { buf = buf.copyOfRange(n, buf.size); droppedBytes += n }

        @Synchronized
        fun feed(data: ByteArray): List<Frame> {
            val now = System.nanoTime()
            if (buf.isNotEmpty() && (now - last) / 1_000_000 > timeoutMs) { droppedBytes += buf.size; buf = ByteArray(0) }
            last = now
            buf += data
            val out = ArrayList<Frame>()
            while (buf.isNotEmpty()) {
                val b0 = buf[0].toInt() and 0xFF
                if (b0 != 2 && b0 != 3 && b0 != 4) { drop(1); continue }
                val start = b0           // 1 + (b0 - 1) octets de longueur
                if (buf.size < start) break
                var ln = 0
                for (i in 1 until start) ln = (ln shl 8) or (buf[i].toInt() and 0xFF)
                if ((b0 == 2 && ln < 1) || (b0 == 3 && ln < 255) || (b0 == 4 && ln < 65535) || ln > MAX_PAYLOAD) { drop(1); continue }
                val total = start + ln + 3
                if (buf.size < total) break
                val raw = buf.copyOfRange(0, total)
                val payload = raw.copyOfRange(start, start + ln)
                val crcRx = ((raw[start + ln].toInt() and 0xFF) shl 8) or (raw[start + ln + 1].toInt() and 0xFF)
                val crcCalc = crc16(payload)
                if (raw[total - 1].toInt() != 3) { drop(1); out.add(Frame(payload, raw, crcRx, crcCalc, false, "octet de fin invalide")); continue }
                if (crcRx != crcCalc) { drop(total); out.add(Frame(payload, raw, crcRx, crcCalc, false, "CRC invalide")); continue }
                drop(total)
                droppedBytes -= total          // trame valide : pas une perte
                out.add(Frame(payload, raw, crcRx, crcCalc, true))
            }
            return out
        }
    }

    // ---- charges utiles (ordre des bits = commands.c)
    private class Field(val name: String, val type: String, val scale: Double)

    private fun f(n: String, t: String, s: Double = 1.0) = Field(n, t, s)

    private val VALUES = listOf(
        0 to listOf(f("temp_fet", "i16", 1e1)), 1 to listOf(f("temp_motor", "i16", 1e1)),
        2 to listOf(f("avg_motor_current", "i32", 1e2)), 3 to listOf(f("avg_input_current", "i32", 1e2)),
        4 to listOf(f("avg_id", "i32", 1e2)), 5 to listOf(f("avg_iq", "i32", 1e2)),
        6 to listOf(f("duty", "i16", 1e3)), 7 to listOf(f("rpm", "i32")), 8 to listOf(f("v_in", "i16", 1e1)),
        9 to listOf(f("amp_hours", "i32", 1e4)), 10 to listOf(f("amp_hours_charged", "i32", 1e4)),
        11 to listOf(f("watt_hours", "i32", 1e4)), 12 to listOf(f("watt_hours_charged", "i32", 1e4)),
        13 to listOf(f("tachometer", "i32")), 14 to listOf(f("tachometer_abs", "i32")),
        15 to listOf(f("fault", "u8")), 16 to listOf(f("pid_pos", "i32", 1e6)), 17 to listOf(f("controller_id", "u8")),
        18 to listOf(f("temp_mos1", "i16", 1e1), f("temp_mos2", "i16", 1e1), f("temp_mos3", "i16", 1e1)),
        19 to listOf(f("avg_vd", "i32", 1e3)), 20 to listOf(f("avg_vq", "i32", 1e3)), 21 to listOf(f("status", "u8"))
    )
    private val SETUP = listOf(
        0 to listOf(f("temp_fet", "i16", 1e1)), 1 to listOf(f("temp_motor", "i16", 1e1)),
        2 to listOf(f("current_tot", "i32", 1e2)), 3 to listOf(f("current_in_tot", "i32", 1e2)),
        4 to listOf(f("duty", "i16", 1e3)), 5 to listOf(f("rpm", "i32")), 6 to listOf(f("speed", "i32", 1e3)),
        7 to listOf(f("v_in", "i16", 1e1)), 8 to listOf(f("battery_level", "i16", 1e3)),
        9 to listOf(f("amp_hours", "i32", 1e4)), 10 to listOf(f("amp_hours_charged", "i32", 1e4)),
        11 to listOf(f("watt_hours", "i32", 1e4)), 12 to listOf(f("watt_hours_charged", "i32", 1e4)),
        13 to listOf(f("distance", "i32", 1e3)), 14 to listOf(f("distance_abs", "i32", 1e3)),
        15 to listOf(f("pid_pos", "i32", 1e6)), 16 to listOf(f("fault", "u8")), 17 to listOf(f("controller_id", "u8")),
        18 to listOf(f("num_vescs", "u8")), 19 to listOf(f("wh_batt_left", "i32", 1e3)),
        20 to listOf(f("odometer", "u32")), 21 to listOf(f("uptime_ms", "u32"))
    )

    private class W {
        val o = ByteArrayOutputStream()
        fun u8(v: Int) = o.write(v and 0xFF)
        fun i16(v: Double, s: Double) { val x = (v * s).toLong().coerceIn(-32768L, 32767L).toInt(); u8(x shr 8); u8(x) }
        fun i32(v: Double, s: Double) {
            val x = (v * s).toLong().coerceIn(Int.MIN_VALUE.toLong(), Int.MAX_VALUE.toLong()).toInt()
            u8(x shr 24); u8(x shr 16); u8(x shr 8); u8(x)
        }
        fun u32(v: Long) { u8((v shr 24).toInt()); u8((v shr 16).toInt()); u8((v shr 8).toInt()); u8(v.toInt()) }
    }

    /** Réponse de COMM_GET_VALUES / _SETUP ; [mask] != null => variante SELECTIVE. */
    fun buildValues(cmd: Int, values: Map<String, Double>, mask: Long? = null): ByteArray {
        val spec = if (cmd == GET_VALUES || cmd == GET_VALUES_SELECTIVE) VALUES else SETUP
        val w = W()
        w.u8(cmd)
        val m = mask ?: 0xFFFFFFFFL
        if (mask != null) w.u32(mask)
        for ((bit, fields) in spec) {
            if (m and (1L shl bit) == 0L) continue
            for (fd in fields) {
                val v = values[fd.name] ?: 0.0
                when (fd.type) {
                    "i16" -> w.i16(v, fd.scale)
                    "i32" -> w.i32(v, fd.scale)
                    "u8" -> w.u8(v.toInt())
                    else -> w.u32(v.toLong())
                }
            }
        }
        return w.o.toByteArray()
    }

    /** COMM_FW_VERSION — disposition de commands.c (v7.01). */
    fun buildFwVersion(major: Int, minor: Int, hwName: String, hwCrc: Long = 0x5EC51A71L): ByteArray {
        val w = W()
        w.u8(FW_VERSION); w.u8(major); w.u8(minor)
        w.o.write(hwName.toByteArray(Charsets.US_ASCII)); w.u8(0)
        for (i in 0 until 12) w.u8(0xA0 + i)            // UUID
        repeat(8) { w.u8(0) }                              // pairing, test ver, hw type, custom cfg, phase filters, qml x2, nrf
        w.u8(0)                                            // FW_NAME vide
        w.u32(hwCrc)
        return w.o.toByteArray()
    }
}
