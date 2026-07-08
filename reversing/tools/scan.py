#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 同目录 dis6502
from dis6502 import PRG, CHR, CDL_PRG, CDL_CHR

def bank_of(off): return off // 0x2000  # 8KB bank index

# ---- CDL code/data coverage per 8KB bank ----
print("=== CDL coverage per 8KB PRG bank (64 banks) ===")
for b in range(64):
    s = b*0x2000; e = s+0x2000
    code = sum(1 for i in range(s,e) if CDL_PRG[i]&1)
    dat  = sum(1 for i in range(s,e) if CDL_PRG[i]&2)
    if code or dat:
        print(f" bank {b:2d} (PRG {s:05X}-{e-1:05X}): code={code:5d} data={dat:5d}")

# ---- search PPU register store patterns ----
# STA/STX/STY absolute to $2006 / $2007
patterns = {
    (0x8D,0x06,0x20):'STA $2006', (0x8E,0x06,0x20):'STX $2006', (0x8C,0x06,0x20):'STY $2006',
    (0x8D,0x07,0x20):'STA $2007', (0x8E,0x07,0x20):'STX $2007', (0x8C,0x07,0x20):'STY $2007',
    (0x9D,0x07,0x20):'STA $2007,X', (0x99,0x07,0x20):'STA $2007,Y',
}
print("\n=== $2006/$2007 store sites (only where CDL marks CODE) ===")
hits = {}
for i in range(len(PRG)-3):
    t = (PRG[i],PRG[i+1],PRG[i+2])
    if t in patterns and (CDL_PRG[i]&1):
        hits.setdefault(patterns[t], []).append(i)
for name, offs in sorted(hits.items()):
    print(f" {name}: {len(offs)} sites -> " + " ".join(f"{o:05X}" for o in offs[:40]))

# ---- MMC5 CHR bank writes $5120-$512B ----
print("\n=== MMC5 CHR-bank register writes ($5120-$512B), CODE only ===")
chrhits = {}
for i in range(len(PRG)-3):
    if PRG[i] in (0x8D,0x8E,0x8C) and PRG[i+2]==0x51 and 0x20 <= PRG[i+1] <= 0x2B and (CDL_PRG[i]&1):
        reg = 0x5100 | PRG[i+1]
        chrhits.setdefault(reg, []).append(i)
for reg, offs in sorted(chrhits.items()):
    print(f" ${reg:04X}: {len(offs)} -> " + " ".join(f"{o:05X}" for o in offs[:30]))

# ---- MMC5 PRG bank writes $5113-$5117 ----
print("\n=== MMC5 PRG-bank register writes ($5113-$5117), CODE only ===")
prghits = {}
for i in range(len(PRG)-3):
    if PRG[i] in (0x8D,0x8E,0x8C) and PRG[i+2]==0x51 and 0x13 <= PRG[i+1] <= 0x17 and (CDL_PRG[i]&1):
        reg = 0x5100 | PRG[i+1]
        prghits.setdefault(reg, []).append(i)
for reg, offs in sorted(prghits.items()):
    print(f" ${reg:04X}: {len(offs)} -> " + " ".join(f"{o:05X}" for o in offs[:30]))

# ---- reset/nmi/irq vectors (last bank at $E000-$FFFF) ----
print("\n=== Vectors (assuming last 8KB bank 63 at $E000-$FFFF) ===")
last = 63*0x2000
nmi = PRG[last+0x1FFA] | (PRG[last+0x1FFB]<<8)
rst = PRG[last+0x1FFC] | (PRG[last+0x1FFD]<<8)
irq = PRG[last+0x1FFE] | (PRG[last+0x1FFF]<<8)
print(f" NMI=${nmi:04X} RESET=${rst:04X} IRQ=${irq:04X}")
