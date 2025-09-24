# autodetect.py — scan COM ports, try common bauds, probe first register
import json
import time
from typing import Optional, Tuple, Dict, Any
from serial.tools import list_ports
from pathlib import Path
import sys

from modbus_client import RTUClient, read_all

COMMON_BAUDS = [115200, 57600, 38400, 19200, 9600]
COMMON_PARITIES = ['N']  # extend if needed: ['N','E','O']

def resource_path(name: str) -> str:
    p1 = Path.cwd() / name
    if p1.exists():
        return str(p1)
    if getattr(sys, 'frozen', False):
        p2 = Path(sys.executable).parent / name
        if p2.exists():
            return str(p2)
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p3 = Path(base) / name
        if p3.exists():
            return str(p3)
    return name

CFG_PATH = resource_path('registers.json')

def load_config(path: str = CFG_PATH) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def _probe_once(port: str, baud: int, parity: str, slave_id: int, endianness: str, probe_reg: Dict[str, Any]) -> bool:
    try:
        cli = RTUClient(port, baud, slave_id, parity=parity)
        time.sleep(0.05)
        regs = [probe_reg]
        data = read_all(cli, regs, endianness)
        name = probe_reg['name']
        val = data.get(name)
        return not (isinstance(val, str) and val.startswith('ERR:'))
    except Exception:
        return False

def autodetect() -> Optional[Tuple[str, int, str]]:
    cfg = load_config()
    slave_id = cfg['slave_id']; endianness = cfg['endianness']
    probe = cfg.get('probe') or cfg['registers'][0]
    ports = [p.device for p in list_ports.comports()]
    for port in ports:
        for parity in COMMON_PARITIES:
            for baud in COMMON_BAUDS:
                if _probe_once(port, baud, parity, slave_id, endianness, probe):
                    return port, baud, parity
    return None
