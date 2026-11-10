# Bluetooth (BLE) — ce qui est possible, et ce qui ne l'est pas

## Ce que fait réellement un VESC en BLE
Le module BLE du VESC (nRF52 / VESC Express) est un **périphérique GATT** exposant le *Nordic UART Service* :

| Élément | UUID |
|---|---|
| Service | `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` |
| RX (le central **écrit** les requêtes) | `6E400002-B5A3-F393-E0A9-E50E24DCCA9E` |
| TX (le périphérique **notifie** les réponses) | `6E400003-B5A3-F393-E0A9-E50E24DCCA9E` |

Les octets transportés sont **exactement les trames VESC UART** (`02 len payload crc 03`), découpées selon le MTU (20 octets par défaut).
Votre ESP32 (tableau de bord) est donc **central/client BLE** ; le simulateur doit être **périphérique/serveur**.
Ce n'est ni du Bluetooth classique (SPP), ni une simple « connexion BLE » : sans le service NUS et les trames VESC, rien ne fonctionne.

## Limite sous Windows
- **Bleak** (dans `requirements.txt`) ne sait agir qu'en *central* : il sert ici au **scan** (diagnostic : voir si l'ESP32/le VESC est visible, repérer `★ NUS`).
- Un serveur GATT est possible via l'API WinRT `GattServiceProvider` (Windows 10/11, adaptateur BLE compatible « peripheral role »).
  `communication/ble_server.py` l'implémente (`WinRtBleServer`) mais cette implémentation est **expérimentale et non validée sur matériel**
  (développée sans Windows). Le **nom** annoncé est celui du PC : l'ESP32 doit filtrer sur l'UUID du service, pas sur le nom.

## Solution recommandée (fiable) : pont ESP32 « BLE ⇄ UART »
Un 2ᵉ ESP32 (ESP32‑S3 ou autre) fait office de **faux module BLE VESC** : périphérique NUS côté radio, UART côté PC.
Le tableau de bord se connecte en BLE à ce pont comme à un vrai VESC ; le simulateur dialogue en **UART** (adaptateur USB ou USB natif du pont).

```cpp
// ESP32 pont — NimBLE-Arduino. Transmet tel quel BLE(RX) -> UART et UART -> BLE(TX notify).
#include <NimBLEDevice.h>
#define SVC "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define RXC "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define TXC "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
NimBLECharacteristic *tx;
class RxCb : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic *c) { std::string v = c->getValue(); Serial.write((const uint8_t*)v.data(), v.size()); }
};
void setup() {
  Serial.begin(115200);                      // UART0/USB vers le PC (simulateur)
  NimBLEDevice::init("VESC SIM");
  NimBLEServer *s = NimBLEDevice::createServer();
  NimBLEService *svc = s->createService(SVC);
  tx = svc->createCharacteristic(TXC, NIMBLE_PROPERTY::NOTIFY);
  svc->createCharacteristic(RXC, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_NR)->setCallbacks(new RxCb());
  svc->start();
  NimBLEAdvertising *a = NimBLEDevice::getAdvertising(); a->addServiceUUID(SVC); a->start();
}
void loop() {
  static uint8_t buf[20]; size_t n = 0;
  while (Serial.available() && n < sizeof buf) buf[n++] = Serial.read();
  if (n) { tx->setValue(buf, n); tx->notify(); }
  delay(2);
}
```
Dans le simulateur : *Communication → port du pont → Connecter* (115 200 bauds). Le journal affiche alors les trames reçues via BLE.
Remarque : le débit effectif BLE (20 octets/notification) limite le taux de rafraîchissement ; augmenter le MTU côté pont si besoin.
