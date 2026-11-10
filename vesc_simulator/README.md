# VESC SIMULATOR PRO

Simulateur de contrôleur **VESC** (télémétrie seule) pour tester un tableau de bord **ESP32‑S3 / ESP32‑P4**.
L'ESP32 interroge le PC en UART comme s'il parlait à un vrai VESC ; le logiciel répond avec de **vraies trames du protocole VESC**
(framing + CRC16 + charges utiles `COMM_*`) construites à partir du firmware officiel ([vedderb/bldc](https://github.com/vedderb/bldc) v7.01).

> ⚠️ **Simulateur uniquement.** Aucune commande de pilotage/configuration n'est traitée ni émise (voir *Sécurité*).

## Installation (Windows 10/11)
```bat
py -3.12 -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
**Exécutable `.exe`** : `build_exe.bat` (PyInstaller) → `dist\VESC_SIMULATOR_PRO\VESC_SIMULATOR_PRO.exe`.
Sans Windows sous la main : le workflow GitHub `.github/workflows/build-windows-exe.yml` construit le `.exe` sur un runner Windows
(onglet *Actions* → *Build VESC SIMULATOR PRO* → *Artifacts* → `VESC_SIMULATOR_PRO_windows.zip`).
> Il n'existe pas de fichier APK : c'est une application **Windows**. (PyInstaller ne compile pas en croisé depuis Linux.)

## Démarrage rapide
1. `python main.py` → **START SIMULATION**, scénario *Accélération* (onglet *Scénarios*).
2. Onglet **Communication** : choisir le port COM de l'adaptateur USB‑UART → **Connecter** (voir `docs/UART.md`).
   Sans matériel : **Démarrer l'ESP32 virtuel**.
3. Onglet **DASHBOARD TEST** : *Appliquer le vecteur de référence* (500 tr/min, 48,0 V, 10,0 A, 55 °C/40 °C, 50 %)
   et comparer avec l'écran physique ; *Test déconnexion* pour vérifier perte et retour de liaison.

## Fonctions
| Zone | Contenu |
|---|---|
| Barre d'état | VESC CONNECTÉ/DÉCONNECTÉ, RUNNING/STOPPED/PAUSE, type de liaison, port COM, adresse BLE, fréquence des requêtes, temps simulé |
| Tableau de bord | 12 grandeurs temps réel, 6 graphiques (RPM, vitesse, tension, intensité, puissance, températures), curseurs de forçage (RPM, vitesse, tension, intensité, temp. moteur/MOSFET, niveau batterie) appliqués immédiatement |
| Commandes | START / STOP / PAUSE / RESET, mode ralenti ×0,25 / normal / accéléré ×4 |
| Scénarios | 1 Démarrage · 2 Accélération · 3 Décélération · 4 Batterie faible · 5 Surchauffe · 6 Forte accélération · 7 Freinage régénératif · 8 Défauts (surtension, sous‑tension, surchauffe, surintensité, défaut de communication, erreur moteur) · 9 Perte de connexion |
| Réglages & profils | batterie 36/48/52/60/72/84 V (nominale/max/min, Ah, Wh, charge, résistance interne), moteur (pôles, puissances, couple), contrôleur, véhicule ; profils JSON (`profiles/`) |
| Diagnostic | chaque trame RX/TX : heure, ID, taille, CRC calculé/reçu, validation, hex ; journal des erreurs CRC, commandes inconnues/bloquées, octets perdus, fréquence ; export ; fichier `logs/vesc_AAAAMMJJ.log` |
| DASHBOARD TEST | vérifications automatiques (connexion, RPM, tension, courant, températures, batterie, défauts, déconnexion, retour), tableau « envoyé / codé dans la trame » |
| Communication | UART/USB (débit configurable, défaut 115 200), ESP32 virtuel, BLE (voir limites), CAN (extension) |

## Protocole (vérifié sur le firmware)
- **Trame** : `0x02 len(1)` | `0x03 len(2)` | `0x04 len(3)` + payload + `CRC16 (poly 0x1021, init 0, big‑endian)` + `0x03` (`comm/packet.c`, `util/crc.c`).
- **Réponses** : `COMM_FW_VERSION`(0), `COMM_GET_VALUES`(4), `COMM_GET_VALUES_SETUP`(47) et variantes `_SELECTIVE`(50/51, masque 32 bits) ;
  champs, ordre, tailles et facteurs d'échelle repris de `comm/commands.c` (entiers big‑endian, `valeur × échelle`).
- **Conventions** : RPM envoyé = ERPM (tr/min × paires de pôles) ; vitesse en m/s ; courant batterie > 0 = décharge, < 0 = régénération ; défaut = codes `mc_fault_code`.
- **Validations réalisées**
  - `tools/verify_with_firmware.py` compile le **code C officiel** `crc.c`/`packet.c` : il encode et décode les mêmes trames que le simulateur (✔ identique) et rejette un CRC invalide.
  - Trames de référence VESC Tool : `02 01 04 40 84 03` (GET_VALUES), `02 01 00 00 00 03` (FW_VERSION) ; CRC comparé à `binascii.crc_hqx`.
  - Client indépendant « VescUart‑like » (`tests/vescuart_client.py`, CRC bit à bit, décodage à offsets fixes) sur un **vrai port série** (pty) : 300 requêtes consécutives, bruit, octets isolés, perte/retour de liaison, reconnexion du port.
  - `pytest -q tests` → 57 tests.
- Les **dispositions de charge utile** (GET_VALUES, SETUP, FW_VERSION) sont écrites d'après la lecture de `commands.c` ; elles n'ont pas été exécutées contre le firmware complet (qui nécessite la chaîne ChibiOS/STM32). **Validez finalement avec votre ESP32** (`docs/ESP32.md`).

## Sécurité
Mode **télémétrie seule**, non désactivable : seules `FW_VERSION`, `GET_VALUES(_SELECTIVE)`, `GET_VALUES_SETUP(_SELECTIVE)`, `PING_CAN`, `FORWARD_CAN` (nœud simulé) et `ALIVE` sont traitées.
`SET_DUTY/CURRENT/RPM/POS…`, `SET_MCCONF/APPCONF`, `REBOOT`, bootloader/mise à jour, terminal, détection moteur… sont **ignorées et journalisées** (« BLOQUÉE »).
Le simulateur n'émet de toute façon que des réponses/télémétrie.

## Limites et alternatives (à lire)
- **.exe** : non généré dans l'environnement de développement (Linux). Utiliser `build_exe.bat` ou le workflow GitHub.
- **BLE** : le VESC est un *périphérique* NUS ; Bleak (client) ne peut pas l'émuler. Un serveur GATT WinRT expérimental est fourni (non validé sur matériel). Solution fiable : pont ESP32 BLE⇄UART (`docs/BLUETOOTH.md`).
- **CAN** : diffusion des STATUS 1‑5 + PING/PONG (python‑can, formats vérifiés dans `comm_can.c`). Les commandes `COMM_*` encapsulées en CAN (PROCESS_SHORT_BUFFER) ne sont **pas** émulées.
- **Non émulés** (volontairement, structures non inventées) : `GET_MCCONF`, `GET_APPCONF`, IMU, PPM/ADC décodés.
- **UART physique** : un adaptateur USB‑UART 3,3 V est nécessaire (`docs/UART.md`). Sous Windows, ports virtuels : com0com.
- Les tests `pty` (UART réel) ne s'exécutent que sous Linux/macOS ; sous Windows ils sont ignorés (les autres tests passent).

## Architecture
```
main.py                       point d'entrée
simulator/   vesc_engine.py   physique (véhicule, thermique, défauts, forçages)   battery_model.py  OCV + résistance interne
             telemetry.py     grandeurs → champs VESC       scenarios.py  9 scénarios     profiles.py  profils JSON
             dashboard_test.py  vérifications DASHBOARD TEST
communication/ vesc_protocol.py  CRC, framing, builders/parsers   responder.py  requête → réponse (indépendant du transport)
             uart_server.py  pyserial     ble_server.py  NUS / WinRT     can_interface.py  python-can
             frame_log.py    journal + stats     virtual_esp32.py  client de test
interface/   main_window, dashboard, settings, diagnostics, comm_panel, charts, theme
profiles/    *.json (36/48/52/60/72/84 V + personnalisée)       logs/   journaux
tests/       test_crc, test_protocol, test_telemetry, test_scenarios, test_uart_loopback, test_dashboard_can
tools/       verify_with_firmware.py       docs/  UART.md, BLUETOOTH.md, ESP32.md
```

## Tests
```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q tests
python tools/verify_with_firmware.py     # nécessite gcc + Internet
```
