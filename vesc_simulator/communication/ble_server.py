"""BLE : transport "Nordic UART Service" (NUS) utilisé par le module BLE du VESC (nRF52 / VESC Express).

IMPORTANT (lire docs/BLUETOOTH.md)
  - Le tableau de bord ESP32 est le CENTRAL (client) ; le VESC / module BLE est le PÉRIPHÉRIQUE (serveur GATT).
    Le simulateur doit donc se comporter en PÉRIPHÉRIQUE. Bleak est un client uniquement : il ne peut pas
    l'émuler (il sert ici au scan de diagnostic).
  - Service  6E400001-B5A3-F393-E0A9-E50E24DCCA9E
    RX (écriture, central -> VESC)  6E400002-...      TX (notification, VESC -> central)  6E400003-...
    Les trames VESC (02 len payload crc 03) transitent telles quelles, découpées selon le MTU.
  - Sous Windows 10/11 un GATT serveur est possible via WinRT (paquets winrt-*) : implémentation fournie
    ci-dessous, EXPÉRIMENTALE et NON VALIDÉE sur matériel (développée hors Windows).
    Limite connue : le nom diffusé est celui du PC (non modifiable) ; l'ESP32 doit filtrer sur l'UUID du service.
  - Solution de contournement recommandée : pont ESP32 "BLE périphérique <-> UART" (docs/BLUETOOTH.md).
"""
from __future__ import annotations

import asyncio
import threading
import uuid

from communication.responder import VescResponder

NUS_SERVICE = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_RX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"   # le central écrit ici
NUS_TX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"   # le périphérique notifie ici
DEFAULT_CHUNK = 20                                  # MTU 23 - 3


def chunk(data: bytes, size: int = DEFAULT_CHUNK) -> list[bytes]:
    return [data[i:i + size] for i in range(0, len(data), size)]


async def scan(timeout: float = 5.0) -> list[tuple[str, str, list[str]]]:
    """Diagnostic : liste les périphériques BLE visibles (bleak)."""
    from bleak import BleakScanner
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    return [(d.address, d.name or "", list(a.service_uuids)) for d, a in found.values()]


class WinRtBleServer:
    """Serveur GATT NUS via WinRT (Windows uniquement, expérimental)."""

    def __init__(self, responder: VescResponder, chunk_size: int = DEFAULT_CHUNK):
        self.responder = responder
        self.chunk_size = chunk_size
        self.running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._provider = self._tx = None
        self.error = ""

    @staticmethod
    def available() -> bool:
        try:
            import winrt.windows.devices.bluetooth.genericattributeprofile  # noqa: F401
            return True
        except Exception:
            return False

    def start(self) -> None:
        if not self.available():
            raise RuntimeError("WinRT indisponible : pip install winrt-runtime "
                               "winrt-Windows.Devices.Bluetooth.GenericAttributeProfile "
                               "winrt-Windows.Storage.Streams winrt-Windows.Foundation")
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ble-gatt")
        self._thread.start()

    def stop(self) -> None:
        self.running = False
        if self._provider is not None:
            try:
                self._provider.stop_advertising()
            except Exception:
                pass
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._setup())
            self.running = True
            self._loop.run_forever()
        except Exception as exc:
            self.error = str(exc)
            self.responder.log.info(f"BLE : erreur {exc}", "ERR", "BLE")

    async def _setup(self) -> None:
        from winrt.windows.devices.bluetooth.genericattributeprofile import (
            GattCharacteristicProperties, GattLocalCharacteristicParameters, GattProtectionLevel,
            GattServiceProvider, GattServiceProviderAdvertisingParameters)
        from winrt.windows.storage.streams import DataReader, DataWriter

        res = await GattServiceProvider.create_async(uuid.UUID(NUS_SERVICE))
        prov = res.service_provider
        p_rx = GattLocalCharacteristicParameters()
        p_rx.characteristic_properties = (GattCharacteristicProperties.WRITE |
                                          GattCharacteristicProperties.WRITE_WITHOUT_RESPONSE)
        p_rx.write_protection_level = GattProtectionLevel.PLAIN
        p_tx = GattLocalCharacteristicParameters()
        p_tx.characteristic_properties = GattCharacteristicProperties.NOTIFY
        rx = (await prov.service.create_characteristic_async(uuid.UUID(NUS_RX), p_rx)).characteristic
        tx = (await prov.service.create_characteristic_async(uuid.UUID(NUS_TX), p_tx)).characteristic
        self._tx, self._provider = tx, prov
        loop = self._loop

        def on_write(sender, args):
            deferral = args.get_deferral()

            async def handle():
                req = await args.get_request_async()
                reader = DataReader.from_buffer(req.value)
                data = self._read(reader, req.value.length)
                for frame in self.responder.feed(data):
                    for part in chunk(frame, self.chunk_size):
                        w = DataWriter()
                        w.write_bytes(part)
                        await tx.notify_value_async(w.detach_buffer())
                try:
                    req.respond()
                except Exception:
                    pass
                deferral.complete()
            asyncio.run_coroutine_threadsafe(handle(), loop)

        rx.add_write_requested(on_write)
        adv = GattServiceProviderAdvertisingParameters()
        adv.is_connectable = True
        adv.is_discoverable = True
        prov.start_advertising(adv)
        self.responder.log.info("BLE : service NUS publié (expérimental)", "INFO", "BLE")

    @staticmethod
    def _read(reader, n: int) -> bytes:
        buf = bytearray(n)
        reader.read_bytes(buf)
        return bytes(buf)
