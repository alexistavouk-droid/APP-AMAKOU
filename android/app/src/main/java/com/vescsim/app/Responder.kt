package com.vescsim.app

import java.util.Random

class LogEntry(
    val ts: Long, val dir: String, val cmdId: Int, val cmdName: String, val size: Int,
    val crcCalc: Int?, val crcRx: Int?, val valid: Boolean?, val hex: String, val msg: String
)

class FrameLog(private val max: Int = 300) {
    private val items = ArrayDeque<LogEntry>()
    private val times = HashMap<Int, ArrayDeque<Long>>()
    @Volatile var rx = 0; @Volatile var tx = 0; @Volatile var crcErrors = 0
    @Volatile var blocked = 0; @Volatile var unknown = 0; @Volatile var unsupported = 0
    @Volatile var lastRxMs = 0L
    private val counts = HashMap<Int, Int>()
    @Synchronized fun count(id: Int) = counts[id] ?: 0

    @Synchronized fun add(e: LogEntry) {
        items.addLast(e); while (items.size > max) items.removeFirst()
        when (e.dir) {
            "RX" -> {
                rx++; lastRxMs = e.ts; counts[e.cmdId] = (counts[e.cmdId] ?: 0) + 1
                if (e.valid == false) crcErrors++
                val q = times.getOrPut(e.cmdId) { ArrayDeque() }
                q.addLast(e.ts); while (q.size > 30) q.removeFirst()
            }
            "TX" -> tx++
        }
    }

    fun info(msg: String, dir: String = "INFO") = add(LogEntry(System.currentTimeMillis(), dir, -1, "", 0, null, null, null, "", msg))

    @Synchronized fun tail(n: Int): List<LogEntry> = items.toList().takeLast(n)

    /** Fréquence moyenne (Hz) des requêtes valeurs. */
    @Synchronized fun rateHz(): Double {
        val q = times[Vesc.GET_VALUES] ?: times[Vesc.GET_VALUES_SETUP] ?: return 0.0
        if (q.size < 2) return 0.0
        val span = (q.last() - q.first()) / 1000.0
        return if (span > 0) (q.size - 1) / span else 0.0
    }

    @Synchronized fun clear() { items.clear(); times.clear(); counts.clear(); rx = 0; tx = 0; crcErrors = 0; blocked = 0; unknown = 0; unsupported = 0 }
}

/** Répondeur VESC indépendant du transport : octets reçus -> trames à renvoyer. */
class Responder(private val engine: Engine, val log: FrameLog) {
    val decoder = Vesc.Decoder()
    private val rng = Random()

    private fun hex(b: ByteArray) = b.joinToString(" ") { "%02x".format(it.toInt() and 0xFF) }

    fun feed(data: ByteArray): List<ByteArray> {
        val out = ArrayList<ByteArray>()
        for (f in decoder.feed(data)) out += handle(f)
        return out
    }

    fun handle(fr: Vesc.Frame): List<ByteArray> {
        val now = System.currentTimeMillis()
        val cid = fr.cmdId
        log.add(LogEntry(now, "RX", cid, Vesc.name(cid), fr.payload.size, fr.crcCalc, fr.crcRx, fr.ok, hex(fr.raw), fr.error))
        if (!fr.ok) { log.info("Erreur CRC : reçu %04X, calculé %04X".format(fr.crcRx, fr.crcCalc), "ERR"); return emptyList() }
        val link = engine.link
        if (!link.up) { log.info("Liaison coupée (simulation) : requête ignorée", "WARN"); return emptyList() }
        if (link.dropRate > 0 && rng.nextDouble() < link.dropRate) { log.info("Défaut simulé : réponse perdue", "WARN"); return emptyList() }
        val reply = process(fr.payload) ?: return emptyList()
        var frame = Vesc.frame(reply)
        if (link.crcCorruptRate > 0 && rng.nextDouble() < link.crcCorruptRate) {
            frame = frame.copyOf(); frame[frame.size - 3] = (frame[frame.size - 3].toInt() xor 0xFF).toByte()
            log.info("Défaut simulé : CRC de la réponse corrompu", "WARN")
        }
        val c = Vesc.crc16(reply)
        log.add(LogEntry(System.currentTimeMillis(), "TX", reply[0].toInt() and 0xFF, Vesc.name(reply[0].toInt() and 0xFF), reply.size, c, c, true, hex(frame), ""))
        return listOf(frame)
    }

    fun process(payload: ByteArray): ByteArray? {
        val cid = payload[0].toInt() and 0xFF
        val data = payload.copyOfRange(1, payload.size)
        when (cid) {
            Vesc.FORWARD_CAN -> {
                if (data.isEmpty()) return null
                if ((data[0].toInt() and 0xFF) != engine.controllerId) { log.info("FORWARD_CAN vers un autre nœud : ignoré"); return null }
                return if (data.size > 1) process(data.copyOfRange(1, data.size)) else null
            }
            Vesc.FW_VERSION -> return Vesc.buildFwVersion(engine.fwMajor, engine.fwMinor, engine.hwName)
            Vesc.GET_VALUES, Vesc.GET_VALUES_SETUP -> return values(cid, null)
            Vesc.GET_VALUES_SELECTIVE, Vesc.GET_VALUES_SETUP_SELECTIVE -> {
                if (data.size < 4) { log.info("Requête SELECTIVE sans masque", "ERR"); return null }
                var m = 0L
                for (i in 0 until 4) m = (m shl 8) or (data[i].toLong() and 0xFF)
                return values(cid, m)
            }
            Vesc.PING_CAN -> return byteArrayOf(Vesc.PING_CAN.toByte())
            Vesc.ALIVE -> return null
        }
        if (cid in Vesc.BLOCKED) { log.blocked++; log.info("${Vesc.name(cid)} BLOQUÉE : télémétrie seule", "WARN"); return null }
        if (cid in Vesc.UNSUPPORTED) { log.unsupported++; log.info("${Vesc.name(cid)} : lecture non émulée", "WARN"); return null }
        log.unknown++; log.info("Commande non reconnue : id=$cid", "WARN")
        return null
    }

    private fun values(cid: Int, mask: Long?): ByteArray {
        val t = engine.snapshot()
        val m = if (cid == Vesc.GET_VALUES || cid == Vesc.GET_VALUES_SELECTIVE) t.vescValues() else t.setupValues()
        return Vesc.buildValues(cid, m, mask)
    }
}
