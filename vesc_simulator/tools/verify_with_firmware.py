"""Vérification croisée avec le CODE C OFFICIEL du firmware VESC (crc.c + packet.c).

Télécharge util/crc.c, util/crc.h, comm/packet.c, comm/packet.h depuis github.com/vedderb/bldc, les compile
avec gcc (-DNO_STM32) puis :
  1. fait encoder des charges utiles par packet_send_packet() et compare avec communication.vesc_protocol ;
  2. fait décoder par packet_process_byte() les trames produites par le simulateur ;
  3. vérifie que le firmware rejette une trame au CRC invalide.
Usage :  python tools/verify_with_firmware.py        (nécessite gcc et un accès Internet)
Les fichiers GPL téléchargés restent dans un dossier temporaire (non versionnés).
"""
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from communication import vesc_protocol as P  # noqa: E402
from simulator.telemetry import Telemetry  # noqa: E402

BASE = "https://raw.githubusercontent.com/vedderb/bldc/master/"
FILES = ["util/crc.c", "util/crc.h", "comm/packet.c", "comm/packet.h"]
HARNESS = r'''
#include <stdio.h>
#include "packet.h"
static PACKET_STATE_t st;
static void send_f(unsigned char *d, unsigned int n){ for(unsigned i=0;i<n;i++) printf("%02x",d[i]); printf("\n"); }
static void proc(unsigned char *d, unsigned int n){ printf("OK %u\n", n); }
int main(void){ packet_init(send_f, proc, &st); char line[4096];
  while (fgets(line,sizeof line,stdin)) { unsigned char buf[2048]; int n=0;
    for (char*p=line+2; p[0]&&p[1]&&p[0]!='\n'; p+=2){ unsigned v; sscanf(p,"%2x",&v); buf[n++]=v; }
    if(line[0]=='E') packet_send_packet(buf,n,&st); else { for(int i=0;i<n;i++) packet_process_byte(buf[i],&st); printf("DONE\n"); } } }
'''


def main() -> int:
    d = Path(tempfile.mkdtemp(prefix="vesc_fw_"))
    for f in FILES:
        (d / Path(f).name).write_bytes(urllib.request.urlopen(BASE + f, timeout=30).read())
    (d / "h.c").write_text(HARNESS)
    exe = d / "oracle"
    subprocess.run(["gcc", "-DNO_STM32", "-I", str(d), "-o", str(exe), str(d / "h.c"), str(d / "packet.c"),
                    str(d / "crc.c")], check=True)
    t = Telemetry(erpm=12345, v_in=52.1, i_batt=11.2, temp_fet=40.5)
    payloads = [b"\x04", b"\x00", bytes(range(1, 100)), bytes([7]) * 300,
                P.build_values_payload(P.COMM_GET_VALUES, t.vesc_values()),
                P.build_values_payload(P.COMM_GET_VALUES_SETUP, t.vesc_setup_values()),
                P.build_fw_version(P.FwInfo())]
    run = lambda txt: subprocess.run([str(exe)], input=txt, capture_output=True, text=True).stdout.split("\n")
    enc = [x for x in run("".join(f"E {p.hex()}\n" for p in payloads)) if x]
    ok1 = enc == [P.frame_packet(p).hex() for p in payloads]
    dec = [x for x in run("".join(f"D {P.frame_packet(p).hex()}\n" for p in payloads)) if x.startswith("OK")]
    ok2 = dec == [f"OK {len(p)}" for p in payloads]
    bad = bytearray(P.frame_packet(payloads[4])); bad[10] ^= 1
    ok3 = not any(x.startswith("OK") for x in run(f"D {bad.hex()}\n"))
    print(f"encodage firmware == simulateur : {ok1}\nfirmware accepte nos trames    : {ok2}\n"
          f"firmware rejette CRC invalide  : {ok3}")
    return 0 if ok1 and ok2 and ok3 else 1


if __name__ == "__main__":
    sys.exit(main())
