#!/usr/bin/env python3
"""B 命门验证：让对话框(文本段)切到扩 CHR 的专属新 bank 128。

改动：
1. 扩 CHR 512KB→1MB；
2. bank 128 = 复制 bank 0（保留假名/标点），0xB0+ 写中文字模；
3. NMI 改一处（等长）：LDA $0451 → LDA #128，使 region-1(对话框)影子 $045F=128；
   region-0(机甲, $045E←$0450=48)不受影响；bank 0 原封不动。
4. 句 62 文本回写（码位 0xB0+）。

判读：对话框显示正确中文 = 用了 bank128 = 命门通；显示"以井宇…"(bank0 原汉字) = 没走 128。
"""
from reinsert import solve_text, glyph_tile, TRANS
from msgtool import Rom, DOUBLE_BYTE, TRIPLE_BYTE

SRC = "Metal Slader Glory (Japan).nes"
OUT = "MSG-b-demo.nes"
CHR0 = 0x10 + 512 * 1024
STR_FREE = 0x06010
NEWBANK = 128
NMI_PATCH = 0x7EB8F           # .nes 偏移：AD 51 04 (LDA $0451)

rom = bytearray(open(SRC, "rb").read())
R = Rom(bytes(rom))

# 1) 扩 CHR 到 1MB
rom[5] = 128
rom += bytes(512 * 1024)

# 2) bank 128 = 复制原版 bank 0（含假名/标点字形）
src = CHR0 + 0 * 4096
dst = CHR0 + NEWBANK * 4096
rom[dst:dst + 4096] = rom[src:src + 4096]

# 3) NMI 等长改：LDA $0451 → LDA #128; NOP  (region-1 影子 = 128)
assert rom[NMI_PATCH:NMI_PATCH + 3] == bytes([0xAD, 0x51, 0x04]), rom[NMI_PATCH:NMI_PATCH + 3].hex()
rom[NMI_PATCH:NMI_PATCH + 3] = bytes([0xA9, NEWBANK, 0xEA])

# 4) 文本回写句 62（字模写 bank128；文本层同 reinsert）
used = set()
for n in range(1, 2782):
    raw = R.sentence_blocks(n); i = 0
    while i < len(raw):
        b = raw[i]
        if b in TRIPLE_BYTE: i += 3
        elif b in DOUBLE_BYTE: i += 2
        elif b == 0x00: i += 1
        elif b < 0x80: used.add(b); i += 1
        else: used.add((b << 8) + raw[i + 1]); i += 2
free = [b for b in range(0x8080, 0x8B58) if b not in used] + [b for b in range(0x20, 0x80) if b not in used]

str_p = STR_FREE
tile_code = 0xB0
assigned = {}   # ch -> (block, code)

def code_for(ch):
    global str_p, tile_code
    if ch not in assigned:
        blk = free.pop(0)
        rom[dst + tile_code*16 : dst + tile_code*16 + 16] = glyph_tile(ch)   # 字模→bank128
        rom[str_p] = tile_code
        t3 = solve_text(str_p, 1)
        str_p += 1
        tp = R.text_pointer(blk)
        rom[tp:tp+3] = t3
        assigned[ch] = (blk, tile_code)
        tile_code += 1
    return assigned[ch][0]

bs = R.block_string_pointer(R.read3(R.sentence_pointer(62)))
orig_len = len(R.sentence_blocks(62))
new = bytearray([0x21])                       # 保留名字「
for ch in TRANS:
    blk = code_for(ch)
    new += bytes([blk]) if blk < 0x80 else bytes([blk >> 8, blk & 0xFF])
new += bytes([0x00])
assert len(new) <= orig_len, f"{len(new)}>{orig_len}"
new += bytes([0x00]) * (orig_len - len(new))
rom[bs:bs + orig_len] = new

open(OUT, "wb").write(rom)
print(f"{OUT}: {len(rom)} bytes（应 0x180010=1.5MB）")
print(f"NMI patch @ .nes 0x{NMI_PATCH:05X}: AD 51 04 → {rom[NMI_PATCH:NMI_PATCH+3].hex()} (LDA #128; NOP)")
print(f"bank128 = 复制 bank0 + {len(assigned)} 个中文；bank0 原封不动")
print("码位:", " ".join(f"{c:02X}={ch}" for ch, (b, c) in assigned.items()))
