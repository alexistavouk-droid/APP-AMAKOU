# Configuration de l'ESP32 (tableau de bord)

## Ce que le simulateur répond
| Requête (payload) | Réponse |
|---|---|
| `COMM_FW_VERSION` (0) | version FW (7.01 par défaut, réglable), nom matériel, UUID, … |
| `COMM_GET_VALUES` (4) / `_SELECTIVE` (50) | températures, courants, duty, **ERPM**, tension, Ah/Wh, tachymètre, défaut, id, temp MOS1‑3, vd, vq, statut |
| `COMM_GET_VALUES_SETUP` (47) / `_SELECTIVE` (51) | idem « setup » : courant total, **vitesse (m/s)**, **niveau batterie (0‑1)**, distance, Wh restants, odomètre, uptime |
| `COMM_PING_CAN` (62) | liste vide (aucun nœud CAN esclave) |
| `COMM_FORWARD_CAN` (34) | traité si l'ID cible = ID du nœud simulé, sinon ignoré |
| `COMM_ALIVE` (30) | accepté, sans réponse (comme le firmware) |

Tout le reste (SET_*, REBOOT, bootloader, SET_MCCONF…) est **bloqué** et journalisé. `GET_MCCONF/GET_APPCONF/IMU` : non émulés.

## Points d'attention côté ESP32
- **ERPM** : `rpm` reçu = tours/min *électriques*. Tr/min mécanique = `rpm / paires_de_pôles` (pôles/2). Réglez les pôles dans *Réglages*.
- **Vitesse** : `GET_VALUES` n'en contient pas ; calculez-la depuis l'ERPM + diamètre de roue, ou utilisez `GET_VALUES_SETUP` (m/s).
- **Courant batterie** : positif = décharge, négatif = recharge/régénération.
- **Niveau batterie** : seul `GET_VALUES_SETUP` le fournit (`battery_level`, 0‑1) ; sinon estimez-le depuis la tension.
- **Tension nominale ≠ mesurée** : 48 V nominal ⇒ 39–54,6 V mesurés ; la tension chute en charge (résistance interne).
- Timeout de liaison : si aucune réponse pendant ~0,5‑1 s, afficher « déconnecté » ; vérifier la reprise (scénario 9 / *Test déconnexion*).

## Exemple minimal (Arduino, bibliothèque VescUart)
```cpp
#include <VescUart.h>
VescUart UART;
void setup() {
  Serial.begin(115200);
  Serial2.begin(115200, SERIAL_8N1, /*RX*/18, /*TX*/17);   // adapter aux broches câblées
  UART.setSerialPort(&Serial2);
}
void loop() {
  if (UART.getVescValues()) {
    float polePairs = 15;                                   // 30 pôles
    Serial.printf("rpm=%.0f V=%.1f Ibat=%.1f Tfet=%.1f err=%d\n",
                  UART.data.rpm / polePairs, UART.data.inpVoltage, UART.data.avgInputCurrent,
                  UART.data.tempMosfet, (int)UART.data.error);
  } else Serial.println("VESC: pas de réponse");
  delay(100);
}
```
