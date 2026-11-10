package com.vescsim.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder

/** Service de premier plan : garde la simulation et le Bluetooth actifs quand l'app est en arrière-plan. */
class SimService : Service() {
    override fun onBind(i: Intent?): IBinder? = null

    override fun onStartCommand(i: Intent?, flags: Int, startId: Int): Int {
        try {
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(NotificationChannel("sim", "Simulation VESC", NotificationManager.IMPORTANCE_LOW))
            val pi = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
            val n = Notification.Builder(this, "sim")
                .setContentTitle("VESC SIM actif")
                .setContentText("Bluetooth en cours — touchez pour ouvrir")
                .setSmallIcon(R.drawable.ic_stat).setContentIntent(pi).setOngoing(true).build()
            if (Build.VERSION.SDK_INT >= 29) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
            else startForeground(1, n)
        } catch (_: Exception) {
            stopSelf()          // sans service : le Bluetooth fonctionne quand même, app au premier plan
        }
        return START_NOT_STICKY
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        AppState.peek()?.stopBle()
        stopSelf()
    }

    companion object {
        fun start(c: Context) { try { c.startService(Intent(c, SimService::class.java)) } catch (_: Exception) { } }
        fun stop(c: Context) { try { c.stopService(Intent(c, SimService::class.java)) } catch (_: Exception) { } }
    }
}
