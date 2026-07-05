#!/usr/bin/env python3
"""开场幕 demo（能开机版）：只回写开场句到 bank 128，其余幕保持原样（会乱码，预期）。

与 reinsert_full 的全量版不同——全量版扩了 PRG 且块串 191KB 放不进可达安全区、还越界盖了代码
（0x76010 起是代码），导致绿屏崩溃。本 demo 吸取教训：
- **不扩 PRG**（不碰任何代码），只扩 CHR 到 1MB 给字库 bank 128；
- 开场句（55-100，唯一字 187 < 216 一个 bank 装下）→ bank 128；每字一个共享 block；
- 块串 + PPU 串全部落在**已验证安全的空闲区 0x73604-0x76000（~10KB，代码前）**；
- block 从字典槽借用（其他幕因此乱码，但不影响开机与开场）。
"""
from reinsert_full import (tokenize, glyph8x8, ICON_REUSE, CODE_POOL,
                           sentence_chars, load_translation)
from msgtool import Rom

SRC = "Metal Slader Glory (Japan).nes"; OUT = "MSG-zh-demo.nes"
CHR0 = 0x10 + 512 * 1024; NEWBANK = 128
NMI_PATCH = 0x7EB8F
SAFE = (0x73604, 0x76000)          # 可达 + 无代码（块串/PPU 串都放这）
OPENING = range(55, 101)


def solve_text(ptr, length):
    for b1 in range(256):
        for b3 in range(256):
            if ((b1 >> 6) << 3) + (b3 >> 5) != length: continue
            base = (((b1 & 0x3F) - 0x2A) << 13) + (((b3 & 0x1F) ^ 0xA0) << 8)
            b2 = ptr - 0x4A010 - base
            if 0 <= b2 <= 255: return bytes([b1, b2, b3])
    return None


def solve_sentence(addr):
    D = addr - 0x56010
    for b3 in range(256):
        rem = D - ((b3 + 0xA0) << 8)
        if rem < 0: continue
        X, b2 = divmod(rem, 0x2000)
        if b2 > 255: continue
        b1 = X + 0x30
        if 0x30 <= b1 <= 0x7F: return bytes([b1, b2, b3])
    return None


tr = load_translation()
rom = bytearray(open(SRC, "rb").read())
R = Rom(bytes(rom))

# 扩 CHR→1MB（不动 PRG），bank128 = bank0 拷贝
rom[5] = 128
rom += bytes(512 * 1024)
dst = CHR0 + NEWBANK * 4096
rom[dst:dst + 4096] = rom[CHR0:CHR0 + 4096]

# B 命门：对话框 → bank128
assert rom[NMI_PATCH:NMI_PATCH + 3] == bytes([0xAD, 0x51, 0x04])
rom[NMI_PATCH:NMI_PATCH + 3] = bytes([0xA9, NEWBANK, 0xEA])

# 开场唯一字 → 码 + 字模（bank128）
glyphs = set()
for n in OPENING:
    if tr.get(n): glyphs |= sentence_chars(tr[n])
assert len(glyphs) <= len(CODE_POOL), f"{len(glyphs)} > {len(CODE_POOL)}"
char2code = {}
for code, ch in zip(CODE_POOL, sorted(glyphs)):
    char2code[ch] = code
    rom[dst + code * 16: dst + code * 16 + 16] = glyph8x8(ch)

# 每码 → 共享 block（PPU 串=单码位）；block 从字典槽借用（其他幕乱码，预期）
p = SAFE[0]
free_blocks = iter(list(range(0x20, 0x80)) + list(range(0x8080, 0x8B54)))
blk_of = {}
def block_for(code):
    global p
    if code not in blk_of:
        rom[p] = code; t3 = solve_text(p, 1); p += 1
        blk = next(free_blocks)
        rom[R.text_pointer(blk):R.text_pointer(blk) + 3] = t3
        blk_of[code] = blk
    return blk_of[code]

# 回写开场句块串（控制码字节 + 字形 block 序列）
done = 0
for n in OPENING:
    if not tr.get(n): continue
    bs = bytearray()
    for kind, v in tokenize(tr[n]):
        if kind == "ctrl":
            bs += v
        else:
            code = v if kind == "icon" else char2code[v]
            blk = block_for(code)
            bs += bytes([blk]) if blk < 0x80 else bytes([blk >> 8, blk & 0xFF])
    bs.append(0x00)
    assert p + len(bs) <= SAFE[1], f"安全区溢出 @句{n}"
    addr = p; rom[addr:addr + len(bs)] = bs; p += len(bs)
    s3 = solve_sentence(addr)
    assert s3, f"句{n}块串 {addr:X} 不可达"
    rom[R.sentence_pointer(n):R.sentence_pointer(n) + 3] = s3
    done += 1

open(OUT, "wb").write(rom)
print(f"{OUT}: {len(rom)} bytes（PRG 未扩，代码完好）")
print(f"回写开场 {done} 句（{OPENING.start}-{OPENING.stop - 1}）；{len(glyphs)} 唯一字→bank128；"
      f"安全区用 {p - SAFE[0]}/{SAFE[1] - SAFE[0]} 字节")

# round-trip 自验
P = Rom(bytes(rom))
inv = {c: ch for ch, c in char2code.items()}
icon_inv = {v: k for k, v in ICON_REUSE.items()}
bad = 0
for n in OPENING:
    if not tr.get(n): continue
    raw = P.sentence_blocks(n); out = []; i = 0
    from msgtool import DOUBLE_BYTE, TRIPLE_BYTE
    while i < len(raw):
        b = raw[i]
        if b in TRIPLE_BYTE: out.append("~" + raw[i:i+3].hex().upper() + "~"); i += 3
        elif b in DOUBLE_BYTE: out.append("~" + raw[i:i+2].hex().upper() + "~"); i += 2
        elif b == 0x00: break
        else:
            blk = b if b < 0x80 else (b << 8) + raw[i+1]; i += 1 if b < 0x80 else 2
            for c in P.block_ppu(blk):
                out.append(inv.get(c) or icon_inv.get(c) or f"?{c:02X}?")
    if "".join(out) != tr[n]: bad += 1
print(f"round-trip: {done - bad}/{done} 一致" + (" ✓" if not bad else " ✗"))
