import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 同目录 nesrom
from nesrom import CHR, CDL_CHR

def tile(bank4k, t):
    base = bank4k*0x1000 + t*16
    rows=[]
    for y in range(8):
        p0=CHR[base+y]; p1=CHR[base+y+8]
        s=''
        for x in range(8):
            b=((p0>>(7-x))&1)|(((p1>>(7-x))&1)<<1)
            s+=' .oX'[b]
        rows.append(s)
    return rows

for t,label in [(0x20,'0x20 zero'),(0x2A,'0x2A A'),(0x50,'0x50 a-hira'),
                (0xC1,'0xC1 kanji'),(0x0E,'0x0E dakuten-mark'),(0xFE,'0xFE space')]:
    print(f'--- tile {label} (font bank0) ---')
    print('\n'.join(tile(0,t)))

used=0
for b in range(128):
    s=b*0x1000
    if any(CDL_CHR[i] for i in range(s,s+0x1000)):
        used+=1
print('CHR 4KB banks touched in CDL:', used, 'of 128')
