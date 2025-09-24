# modbus_client.py — minimal RTU Modbus wrapper for QMB6Pro
from typing import List, Dict, Any
import minimalmodbus
import serial

class RTUClient:
    def __init__(self, port: str, baudrate: int, slave_id: int, parity: str = 'N', stopbits: int = 1, timeout: float = 0.2):
        self.instrument = minimalmodbus.Instrument(port, slave_id, mode=minimalmodbus.MODE_RTU)
        self.instrument.serial.baudrate = baudrate
        self.instrument.serial.bytesize = 8
        self.instrument.serial.parity = getattr(serial, f'PARITY_{parity}')
        self.instrument.serial.stopbits = stopbits
        self.instrument.serial.timeout = timeout
        self.instrument.clear_buffers_before_each_transaction = True
        self.instrument.close_port_after_each_call = True

    def read_regs(self, address: int, count: int, functioncode: int) -> List[int]:
        return self.instrument.read_registers(address, count, functioncode=functioncode)

    def write_single(self, address: int, value: int, functioncode: int = 6) -> None:
        self.instrument.write_register(address, value, functioncode=functioncode, signed=False)

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
    out: Dict[str, Any] = {}
    for r in regs:
        try:
            t = r['type']; fn = r.get('function', 3); addr = r['address']
            scale = float(r.get('scale', 1.0))
            if t in ('uint16','int16','enum16','bool16','command16','bitmask16'):
                w = cli.read_regs(addr, 1, fn)[0]
                if t == 'bool16':
                    out[r['name']] = bool(w)
                elif t == 'enum16' and 'map' in r:
                    out[r['name']] = r['map'].get(str(w), w)
                elif t == 'bitmask16' and 'map' in r:
                    flags = []
                    for bit_str, label in r['map'].items():
                        mask = int(bit_str)
                        if w & mask: flags.append(label)
                    out[r['name']] = flags
                else:
                    out[r['name']] = (int(w) * scale)
            elif t in ('uint32','int32','ip32','mac48','ascii'):
                if t == 'ascii':
                    words = cli.read_regs(addr, r.get('words', 1), fn)
                    out[r['name']] = words_to_ascii(words)
                else:
                    count = 3 if t == 'mac48' else 2
                    words = cli.read_regs(addr, count, fn)
                    if t == 'ip32':
                        out[r['name']] = words_to_ip(words)
                    elif t == 'mac48':
                        b = [(w >> 8) & 0xFF for w in words] + [w & 0xFF for w in words]
                        out[r['name']] = ':'.join(f"{x:02X}" for x in b[:6])
                    else:
                        be = (endianness == 'big')
                        val = (words[0] << 16) | words[1] if be else (words[1] << 16) | words[0]
                        if t == 'int32' and (val & 0x80000000):
                            val = -((~val & 0xFFFFFFFF) + 1)
                        out[r['name']] = (val * scale)
            else:
                out[r['name']] = 'UNSUPPORTED'
        except Exception as e:
            out[r['name']] = f'ERR:{type(e).__name__}'
    return out

def find_reg(regs: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    for r in regs:
        if r['name'] == name:
            return r
    raise KeyError(name)

def scale_to_raw(val: float, reg: Dict[str, Any]) -> int:
    scale = float(reg.get('scale', 1.0))
    return int(round(val / scale)) if scale != 0 else int(round(val))

def write_u16(cli: RTUClient, addr: int, value: int, fn: int = 6) -> None:
    cli.write_single(addr, int(value), functioncode=fn)
