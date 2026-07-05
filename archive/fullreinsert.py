#!/usr/bin/env python3
"""全量回写编码器（原型）：把句子重新编码进 ROM——重建字典 + 三层指针重算。

策略：每个唯一 PPU 码位 → 一个 block → 一个单码位字符串；每句块串 = 控制码 + block 序列，
全部重建到"可达空闲区"，再改句子指针表/text 表让三层指针指过去。

本原型先验证**编码器逻辑**：用原日文重编码尽量多的句子（受现有可达空闲区 ~5万字节限制），
round-trip 比对 `sentence_text` == 原文。逻辑通过后，全量只需把落点换成扩 PRG 的大空间。
"""
from msgtool import Rom, DOUBLE_BYTE, TRIPLE_BYTE, BLOCK_TEXT_TABLE, SENTENCE_TOTAL

SRC = "Metal Slader Glory (Japan).nes"
FREE_LO, FREE_HI = 0x73604, 0x80010          # 现有可达空闲区（block_string_pointer 可达）

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

rom = bytearray(open(SRC, "rb").read())
R = Rom(bytes(rom))

def tokens(n):
    """句 n → [('c', 控制码字节) | ('p', PPU码位)] 序列。"""
    raw = R.sentence_blocks(n); out = []; i = 0
    while i < len(raw):
        b = raw[i]
        if b in TRIPLE_BYTE: out.append(('c', bytes(raw[i:i+3]))); i += 3
        elif b in DOUBLE_BYTE: out.append(('c', bytes(raw[i:i+2]))); i += 2
        elif b == 0x00: i += 1
        else:
            blk = b if b < 0x80 else (b << 8) + raw[i+1]
            i += 1 if b < 0x80 else 2
            for c in R.block_ppu(blk):
                out.append(('p', c))
    return out

# 空闲区分配器
class Alloc:
    def __init__(s, lo, hi): s.p, s.hi = lo, hi
    def take(s, n):
        if s.p + n > s.hi: raise MemoryError
        a = s.p; s.p += n; return a

alloc = Alloc(FREE_LO, FREE_HI)

# 1) 唯一码位 → block(双字节) + 单码位串 + text 表项
# FIXME(任务B重写时处理)：未排除在用块，且上界应为 0x8B54（idx≥0xB54 的表槽
# 落在句 1108 块串上，见 REVERSING.md）。全量方案改为"一段一块+扩表"后此处作废。
free_blocks = iter(range(0x8080, 0x8B58))
code2block = {}
def block_for(c):
    if c not in code2block:
        blk = next(free_blocks)
        saddr = alloc.take(1); rom[saddr] = c            # 单码位字符串
        t3 = solve_text(saddr, 1)
        tp = R.text_pointer(blk); rom[tp:tp+3] = t3       # block→text→串
        code2block[c] = blk
    return code2block[c]

# 2) 逐句重建块串并重定向（直到空闲区用尽）
done = 0
for n in range(1, SENTENCE_TOTAL + 1):
    toks = tokens(n)
    bs = bytearray()
    try:
        for kind, v in toks:
            if kind == 'c': bs += v
            else:
                blk = block_for(v)
                bs += bytes([blk >> 8, blk & 0xFF])
        bs += b'\x00'
        addr = alloc.take(len(bs))
        s3 = solve_sentence(addr)
        if s3 is None: raise ValueError
        rom[addr:addr+len(bs)] = bs
        rom[R.sentence_pointer(n):R.sentence_pointer(n)+3] = s3
        done = n
    except (MemoryError, ValueError):
        break

print(f"重编码 {done} 句（受现有可达空闲区 {FREE_HI-FREE_LO} 字节限制）")
print(f"唯一码位/block 数: {len(code2block)}；空闲区用了 {alloc.p-FREE_LO} 字节")

# 3) round-trip：patched ROM 前 done 句的 sentence_text 应 == 原文
P = Rom(bytes(rom))
ok = bad = 0; first_bad = None
for n in range(1, done + 1):
    if P.sentence_text(n) == R.sentence_text(n): ok += 1
    else:
        bad += 1
        if first_bad is None: first_bad = n
print(f"round-trip: {ok} 一致 / {bad} 不一致" + (f"（首个不一致：句 {first_bad}）" if bad else " ✓"))
if first_bad:
    print("  原:", R.sentence_text(first_bad)[:60])
    print("  新:", P.sentence_text(first_bad)[:60])
