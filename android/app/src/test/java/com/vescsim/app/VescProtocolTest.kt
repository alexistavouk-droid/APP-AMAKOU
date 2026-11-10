package com.vescsim.app

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class VescProtocolTest {
    private fun hex(b: ByteArray) = b.joinToString("") { "%02x".format(it.toInt() and 0xFF) }

    @Test fun crcXmodemCheckValue() = assertEquals(0x31C3, Vesc.crc16("123456789".toByteArray()))

    @Test fun referenceFrames() {
        assertEquals("020104408403", hex(Vesc.request(Vesc.GET_VALUES)))
        assertEquals("020100000003", hex(Vesc.request(Vesc.FW_VERSION)))
    }

    @Test fun decoderResyncAndCrc() {
        val d = Vesc.Decoder()
        val stream = byteArrayOf(0xFF.toByte(), 0) + Vesc.request(4) + byteArrayOf(0x99.toByte()) + Vesc.request(0)
        assertEquals(listOf(4, 0), d.feed(stream).filter { it.ok }.map { it.cmdId })
        val bad = Vesc.request(4).also { it[3] = (it[3].toInt() xor 0xFF).toByte() }
        val out = Vesc.Decoder().feed(bad + Vesc.request(0))
        assertEquals(listOf(false, true), out.map { it.ok })
    }

    @Test fun longFrame() {
        val p = ByteArray(300) { it.toByte() }
        val f = Vesc.frame(p)
        assertEquals(3, f[0].toInt()); val o = Vesc.Decoder().feed(f)
        assertTrue(o[0].ok); assertArrayEquals(p, o[0].payload)
    }

    // Valeurs de référence produites par la version Python/Windows (vérifiée contre le code C du firmware)
    private fun tel() = Telemetry().apply {
        tempFet = 41.3; tempMotor = 55.5; iMotor = 12.34; iBatt = -3.21; duty = 0.456; erpm = 12345.0
        vIn = 52.4; fault = 5; tachometer = -100
    }

    @Test fun getValuesMatchesPython() =
        assertEquals(GOLDEN_VALUES, hex(Vesc.buildValues(Vesc.GET_VALUES, tel().vescValues())))

    @Test fun getValuesSetupMatchesPython() {
        val t = Telemetry().apply { speedKmh = 36.0; socPct = 87.5; vIn = 50.2; distanceKm = 1.234; odometerM = 5000.0 }
        assertEquals(GOLDEN_SETUP, hex(Vesc.buildValues(Vesc.GET_VALUES_SETUP, t.setupValues())))
    }

    @Test fun fwVersionMatchesPython() = assertEquals(GOLDEN_FW, hex(Vesc.buildFwVersion(7, 1, "HW_TEST")))

    @Test fun getValuesLength() = assertEquals(74, Vesc.buildValues(Vesc.GET_VALUES, tel().vescValues()).size)

    @Test fun selectiveMask() {
        val t = Telemetry().apply { erpm = 777.0; vIn = 48.0 }
        assertEquals(11, Vesc.buildValues(Vesc.GET_VALUES_SELECTIVE, t.vescValues(), (1L shl 7) or (1L shl 8)).size)
    }

    private fun resp() = Responder(Engine().also { it.running = true }, FrameLog())

    @Test fun responderAnswersAndBlocks() {
        val r = resp()
        val out = Vesc.Decoder().feed(r.feed(Vesc.request(4)).first())
        assertTrue(out[0].ok && out[0].payload.size == 74)
        assertTrue(r.feed(Vesc.request(6, byteArrayOf(0, 0, 0x27, 0x10))).isEmpty())
        assertEquals(1, r.log.blocked)
        assertTrue(r.feed(Vesc.request(200)).isEmpty()); assertEquals(1, r.log.unknown)
    }

    @Test fun linkDownGivesNoReply() {
        val e = Engine().also { it.running = true }; val r = Responder(e, FrameLog())
        e.link.up = false
        assertTrue(r.feed(Vesc.request(4)).isEmpty())
    }

    @Test fun physicsSanity() {
        val e = Engine().also { it.running = true }
        e.throttle = 0.8
        repeat(400) { e.step(0.02) }
        val t = e.snapshot()
        assertTrue(t.speedKmh > 10 && t.iBatt > 0 && t.socPct < 100.0)
        assertEquals(t.rpmMech * 15, t.erpm, 1e-6)
        e.setSpeedState(35.0); e.throttle = -0.7
        repeat(100) { e.step(0.02) }
        assertTrue(e.snapshot().iBatt < 0)
    }

    @Test fun scenariosFinish() {
        for (s in Scenarios.all()) {
            val e = Engine().also { it.running = true }
            e.setScenario(s)
            repeat(((s.duration + 1) / 0.05).toInt()) { e.step(0.05) }
            assertTrue(s.name, e.scenario == null)
        }
    }
}

private const val GOLDEN_VALUES = "04019d022b000004d2fffffebf00000000000004d201c800003039020c00000000000000000000000000000000ffffff9c00000000050000000000019d019d019d00000000000035db00"
private const val GOLDEN_SETUP = "2f00fa00fa00000000000000000000000000000000271001f6036b000000000000000000000000000000000012d4500012d45000000000000001000000000000138800000000"
private const val GOLDEN_FW = "00070148575f5445535400a0a1a2a3a4a5a6a7a8a9aaab0000000000000000005ec51a71"
