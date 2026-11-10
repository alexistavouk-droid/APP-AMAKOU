# Guide de branchement UART (PC ⇄ ESP32)

Le simulateur joue le rôle du **VESC** : l'ESP32 envoie des requêtes (`COMM_GET_VALUES`, …) et le PC répond.

## Matériel
- 1 adaptateur **USB‑UART 3,3 V** (CP2102, CH340, FT232 réglé sur 3,3 V). **Jamais de 5 V sur une broche ESP32.**
- 3 fils Dupont.

## Câblage (croisé)
| Adaptateur USB‑UART | ESP32 (tableau de bord) |
|---|---|
| RXD | TX de l'UART « VESC » |
| TXD | RX de l'UART « VESC » |
| GND | GND |
| 3V3 / 5V | **non connecté** (l'ESP32 reste alimenté par son propre câble) |

Broches UART : celles que **votre firmware** utilise pour parler au VESC (ex. ESP32‑S3 : `Serial1`/`Serial2` avec
`RX=18, TX=17`, à adapter ; ESP32‑P4 : n'importe quel UART mappé). Ne pas utiliser l'UART0/USB de flashage.

## Réglages
- 115 200 bauds, 8N1 (défaut du VESC ; réglable dans l'onglet *Communication*, 9 600 → 921 600).
- Windows : *Gestionnaire de périphériques → Ports (COM & LPT)* pour relever le numéro `COMx`.
- Onglet **Communication** → choisir le port → **Connecter** ; le bandeau passe à *CONNECTÉ* dès la 1ʳᵉ requête de l'ESP32.
- Option « Envoi périodique » : pousse `COMM_GET_VALUES` sans requête (utile seulement si votre firmware écoute passivement).

## Test sans ESP32
- Onglet *Communication* → **ESP32 virtuel** (boucle locale logicielle).
- Ou deux ports virtuels reliés (com0com) : simulateur sur `COM10`, un terminal/outil client sur `COM11`.
- Ou un 2ᵉ adaptateur USB‑UART en boucle (TXD1↔RXD2, RXD1↔TXD2, GND↔GND).

## Dépannage
| Symptôme | Cause probable |
|---|---|
| Aucune requête reçue | TX/RX non croisés, mauvais UART/broches, GND manquant, mauvais débit |
| Erreurs CRC | Débit incorrect, parasites, mauvais niveau logique |
| `Commande BLOQUÉE` dans le journal | Votre firmware envoie une commande de pilotage (voulu : ignorée) |
| `Commande non reconnue` | Commande hors périmètre émulé (voir README) |
