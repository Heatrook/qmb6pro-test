# app.py — autostart + czekanie na urządzenie
import json
import time
import argparse
from typing import Dict, Any, List, Tuple

from autodetect import autodetect
from modbus_client import RTUClient
from plotter import LivePlot

CFG_PATH = 'registers.json'

def load_map() -> Dict[str, Any]:
    with open(CFG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def words_to_ascii(words: List[int]) -> str:
    bs = bytearray()
    for w in words:
        bs += bytes([(w >> 8) & 0xFF, w & 0xFF])
    return bs.decode('ascii', errors='ignore').rstrip('\x00').strip()

def words_to_ip(words: List[int]) -> str:
    b = []
    for w in words:
        b.append((w >> 8) & 0xFF); b.append(w & 0xFF)
    return '.'.join(str(x) for x in b)

def read_all(cli: RTUClient, regs: List[Dict[str, Any]], endianness: str) -> Dict[str, Any]:
    out = {}
    for r in regs:
        try:
            t = r['type']; fn = r.get('function', 3); addr = r['address']
            scale = float(r.get('scale', 1.0))
            if t in ('uint16','int16','enum16','bool16','command16'):
                w = cli.read_regs(addr, 1, fn)[0]
                if t == 'bool16':
                    out[r['name']] = bool(w)
                elif t == 'enum16' and 'map' in r:
                    out[r['name']] = r['map'].get(str(w), w)
                else:
                    out[r['name']] = int(w) * scale
            elif t in ('uint32','int32','ip32'):
                words = cli.read_regs(addr, 2, fn)
                if t == 'ip32':
                    out[r['name']] = words_to_ip(words)
                else:
                    be = (endianness == 'big')
                    val = (words[0] << 16) | words[1] if be else (words[1] << 16) | words[0]
                    if t == 'int32' and (val & 0x80000000):
                        val = -((~val & 0xFFFFFFFF) + 1)
                    out[r['name']] = val * scale
            elif t == 'ascii':
                words = cli.read_regs(addr, r.get('words', 1), fn)
                out[r['name']] = words_to_ascii(words)
            else:
                out[r['name']] = 'UNSUPPORTED'
        except Exception as e:
            out[r['name']] = f'ERR:{type(e).__name__}'
    return out

def wait_for_device(slave: int, wait_interval: float, port_override: str | None, baud_override: int | None, parity: str) -> Tuple[str,int,str]:
    """Pętla: czeka aż urządzenie będzie dostępne. Zwraca (port, baud, parity)."""
    shown = False
    while True:
        try:
            if port_override and baud_override:
                # Spróbuj po override
                print(f'Próba połączenia: port={port_override} baud={baud_override} parity={parity}')
                cli = RTUClient(port_override, baud_override, slave, parity=parity)
                # szybki „ping”: odczytaj 1 rejestr z mapy po starcie (zrobimy to w main po załadowaniu cfg)
                return port_override, baud_override, parity
            # Autodetekcja
            det = autodetect()
            if det:
                return det
            if not shown:
                print('Czekam na urządzenie… Podłącz QMB6Pro (RS232/485/USB).')
                shown = True
        except KeyboardInterrupt:
            raise
        except Exception:
            # spokojnie, próbujemy dalej
            pass
        time.sleep(wait_interval)

def main():
    ap = argparse.ArgumentParser(description='QMB6Pro Test App – czeka na urządzenie i startuje po podłączeniu')
    ap.add_argument('--port', help='COM override, np. COM5')
    ap.add_argument('--baud', type=int, help='Baud override, np. 115200')
    ap.add_argument('--parity', default='N', help='N/E/O (default N)')
    ap.add_argument('--scan-interval', type=float, default=2.0, help='co ile sekund próbować ponownie (default 2.0)')
    args = ap.parse_args()

    cfg = load_map()
    regs = cfg['registers']
    endianness = cfg['endianness']
    slave = cfg['slave_id']

    # 1) Czekamy aż urządzenie się pojawi
    port, baud, parity = wait_for_device(slave, args.scan_interval, args.port, args.baud, args.parity)
    print(f'Wykryto urządzenie: port={port} baud={baud} parity={parity} slave={slave}')
    cli = RTUClient(port, baud, slave, parity=parity)

    # 2) Start wykresu po nawiązaniu połączenia
    last_print = time.time()
    def value_fn():
        nonlocal last_print
        data = read_all(cli, regs, endianness)
        ts = time.time()
        if ts - last_print > 1.0:
            print(data)
            last_print = ts
        rate = data.get('CH1_Rate_A_per_s') or data.get('Rate_A_per_s') or 0.0
        if not isinstance(rate, (int, float)):
            rate = 0.0
        return ts, float(rate)

    plot = LivePlot(title='QMB6Pro – CH1 Rate')
    try:
        plot.start(value_fn)
    finally:
        plot.stop()

if __name__ == '__main__':
    main()
