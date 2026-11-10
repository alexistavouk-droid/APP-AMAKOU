package com.vescsim.app

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothGattServer
import android.bluetooth.BluetoothGattServerCallback
import android.bluetooth.BluetoothGattService
import android.bluetooth.BluetoothManager
import android.bluetooth.le.AdvertiseCallback
import android.bluetooth.le.AdvertiseData
import android.bluetooth.le.AdvertiseSettings
import android.content.Context
import android.os.Build
import android.os.ParcelUuid
import java.util.UUID
import java.util.concurrent.ConcurrentLinkedQueue

/**
 * Faux module BLE de VESC : périphérique GATT « Nordic UART Service ».
 * Le tableau de bord (central) écrit les requêtes VESC sur RX et reçoit les réponses par notifications sur TX.
 */
@SuppressLint("MissingPermission")
class BleServer(private val ctx: Context, private val responder: Responder, private val onState: (String) -> Unit) {
    companion object {
        val SERVICE: UUID = UUID.fromString("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
        val RX: UUID = UUID.fromString("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")   // central -> VESC (écriture)
        val TX: UUID = UUID.fromString("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")   // VESC -> central (notification)
        val CCCD: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
        fun chunk(data: ByteArray, size: Int): List<ByteArray> =
            (data.indices step size).map { data.copyOfRange(it, minOf(it + size, data.size)) }
    }

    private val manager = ctx.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
    private var server: BluetoothGattServer? = null
    private var txChar: BluetoothGattCharacteristic? = null
    private var device: BluetoothDevice? = null
    private var mtu = 23
    @Volatile private var notifyEnabled = false
    @Volatile private var advertising = false
    private val queue = ConcurrentLinkedQueue<ByteArray>()
    @Volatile private var sending = false
    var clientName: String = ""; private set
    val isAdvertising get() = advertising
    val isConnected get() = device != null

    fun start(localName: String): String? {
        val adapter = manager.adapter ?: return "Bluetooth indisponible"
        if (!adapter.isEnabled) return "Activez le Bluetooth"
        val adv = adapter.bluetoothLeAdvertiser ?: return "Ce téléphone ne peut pas émettre en BLE (mode périphérique)"
        try { adapter.name = localName } catch (_: Exception) { }
        val srv = manager.openGattServer(ctx, callback) ?: return "Impossible d'ouvrir le serveur GATT"
        server = srv
        val svc = BluetoothGattService(SERVICE, BluetoothGattService.SERVICE_TYPE_PRIMARY)
        val rx = BluetoothGattCharacteristic(RX,
            BluetoothGattCharacteristic.PROPERTY_WRITE or BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE,
            BluetoothGattCharacteristic.PERMISSION_WRITE)
        val tx = BluetoothGattCharacteristic(TX, BluetoothGattCharacteristic.PROPERTY_NOTIFY, BluetoothGattCharacteristic.PERMISSION_READ)
        tx.addDescriptor(BluetoothGattDescriptor(CCCD, BluetoothGattDescriptor.PERMISSION_READ or BluetoothGattDescriptor.PERMISSION_WRITE))
        svc.addCharacteristic(rx); svc.addCharacteristic(tx)
        txChar = tx
        srv.addService(svc)
        val settings = AdvertiseSettings.Builder()
            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
            .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_HIGH)
            .setConnectable(true).setTimeout(0).build()
        val data = AdvertiseData.Builder().setIncludeDeviceName(false).addServiceUuid(ParcelUuid(SERVICE)).build()
        val scan = AdvertiseData.Builder().setIncludeDeviceName(true).build()
        adv.startAdvertising(settings, data, scan, advCallback)
        return null
    }

    fun stop() {
        try { manager.adapter?.bluetoothLeAdvertiser?.stopAdvertising(advCallback) } catch (_: Exception) { }
        try { server?.close() } catch (_: Exception) { }
        server = null; device = null; advertising = false; notifyEnabled = false; queue.clear(); sending = false
        onState("Arrêté")
    }

    private val advCallback = object : AdvertiseCallback() {
        override fun onStartSuccess(settingsInEffect: AdvertiseSettings) { advertising = true; onState("Visible — en attente de l'écran") }
        override fun onStartFailure(errorCode: Int) { advertising = false; onState("Échec de l'annonce BLE (code $errorCode)") }
    }

    private val callback = object : BluetoothGattServerCallback() {
        override fun onConnectionStateChange(dev: BluetoothDevice, status: Int, newState: Int) {
            if (newState == BluetoothGatt.STATE_CONNECTED) {
                device = dev; clientName = try { dev.name ?: dev.address } catch (_: Exception) { dev.address }
                responder.decoder.reset()
                responder.log.info("BLE : client connecté ($clientName)")
                onState("Connecté : $clientName")
            } else {
                device = null; notifyEnabled = false; queue.clear(); sending = false; mtu = 23
                responder.log.info("BLE : client déconnecté", "WARN")
                onState(if (advertising) "Visible — en attente de l'écran" else "Arrêté")
            }
        }

        override fun onMtuChanged(dev: BluetoothDevice, m: Int) { mtu = m; responder.log.info("BLE : MTU $m") }

        override fun onDescriptorWriteRequest(dev: BluetoothDevice, requestId: Int, d: BluetoothGattDescriptor, prepared: Boolean,
                                              responseNeeded: Boolean, offset: Int, value: ByteArray) {
            if (d.uuid == CCCD) {
                notifyEnabled = value.isNotEmpty() && value[0].toInt() != 0
                responder.log.info("BLE : notifications " + if (notifyEnabled) "activées" else "désactivées")
            }
            if (responseNeeded) server?.sendResponse(dev, requestId, BluetoothGatt.GATT_SUCCESS, offset, value)
        }

        override fun onCharacteristicWriteRequest(dev: BluetoothDevice, requestId: Int, c: BluetoothGattCharacteristic, prepared: Boolean,
                                                  responseNeeded: Boolean, offset: Int, value: ByteArray) {
            if (responseNeeded) server?.sendResponse(dev, requestId, BluetoothGatt.GATT_SUCCESS, offset, value)
            if (c.uuid != RX) return
            for (frame in responder.feed(value)) enqueue(frame)
        }

        override fun onNotificationSent(dev: BluetoothDevice, status: Int) { sending = false; pump() }
    }

    @Synchronized private fun enqueue(frame: ByteArray) {
        for (part in chunk(frame, (mtu - 3).coerceAtLeast(20))) queue.add(part)
        pump()
    }

    @Synchronized private fun pump() {
        if (sending) return
        val dev = device ?: return
        val ch = txChar ?: return
        val part = queue.poll() ?: return
        if (!notifyEnabled) { queue.clear(); return }
        sending = true
        val ok = try {
            if (Build.VERSION.SDK_INT >= 33) {
                server?.notifyCharacteristicChanged(dev, ch, false, part) == BluetoothGatt.GATT_SUCCESS
            } else {
                @Suppress("DEPRECATION") run { ch.value = part; server?.notifyCharacteristicChanged(dev, ch, false) == true }
            }
        } catch (_: Exception) { false }
        if (!ok) { sending = false; responder.log.info("BLE : échec d'envoi de notification", "ERR") }
    }
}
