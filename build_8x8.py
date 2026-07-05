#!/usr/bin/env python3
"""8×8 清晰中文（原版引擎，零汇编改动）：字模用缝合怪 fusion-8px 像素字体。

用户定 8×8。引擎选「原来的 8×8 机制」而非「8×16 上下留白」：
- **不打任何 emit patch**（对话 emit 保持原样：上格=$27=FE 空白 tile，下格=字形 tile c）；
- 每字**只占 1 个 tile**（c），每 4KB bank 装 ~238 字（8×16 留白方案要 2 tile/字、只装 63，全量费 4 倍 bank）；
- 字竖直贴下排（cell 行 8..15），与原版假名位置一致，观感原汁原味。
仅有的 ROM 改动 = B 命门（对话框 CHR 区切到扩展 bank128）+ 三层数据回写，均在里程碑 2/3/4 验证。

字形码 c 取值：避开 PPU 层特殊码 0x00(gap)/0x0E/0x0F(浊点) 与空白 tile 0xFE；从 0x10 起。
注意：对话框边框 tile 在高位（实测 0xD1/0xD9 等），全量多 bank 装箱时需按 bank 避让，本 demo 27 字够用。
"""
from PIL import Image, ImageDraw, ImageFont
from reinsert import solve_text
from msgtool import Rom, DOUBLE_BYTE, TRIPLE_BYTE

SRC = "Metal Slader Glory (Japan).nes"; OUT = "MSG-8x8.nes"
FONT = "fonts/fusion-pixel-8px-monospaced-zh_hans.otf"   # OFL 像素字体，随仓库分发
CHR0 = 0x10 + 512 * 1024; NEWBANK = 128
NMI_PATCH = 0x7EB8F; FREE = 0x73604
# 分段=折行锚点（原句自然断句插空块 0x02）
SEGS = ["艾莉娜「这就是这次从阿源", "那儿买来的那台吗总觉得", "挺有意思的呢」"]

_FONT = ImageFont.truetype(FONT, 8)   # 像素字体按设计 px 渲染


def glyph8x8(ch):
    """中文字 → 8×8 tile（下格）。fusion-8px 原生 8×8，无抗锯齿。
    plane0 全 FF；plane1 笔画=位清零（黑底紫字，与原字库一致）。"""
    im = Image.new("L", (8, 8), 0); d = ImageDraw.Draw(im); d.fontmode = "1"
    bb = d.textbbox((0, 0), ch, font=_FONT)
    d.text(((8 - (bb[2] - bb[0])) // 2 - bb[0], 0), ch, fill=255, font=_FONT)
    p1 = bytearray([0xFF] * 8)
    for r in range(8):
        for c in range(8):
            if im.getpixel((c, r)) > 127: p1[r] &= 0xFF ^ (1 << (7 - c))
    return bytes([0xFF] * 8) + bytes(p1)


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

# 1) 扩 CHR 到 1MB；bank128 = bank0 整拷（边框/空白 tile 保留），字模稍后覆盖
rom[5] = 128; rom += bytes(512 * 1024)
dst = CHR0 + NEWBANK * 4096
rom[dst:dst+4096] = rom[CHR0:CHR0+4096]

# 2) B 命门：对话框 region → bank128（唯一的汇编改动，1 处等长）
assert rom[NMI_PATCH:NMI_PATCH+3] == bytes([0xAD, 0x51, 0x04])
rom[NMI_PATCH:NMI_PATCH+3] = bytes([0xA9, NEWBANK, 0xEA])

# 3) 真正空闲 block 槽（仅未引用的单字节 0x20-0x7F）
used = set()
for n in range(1, 2782):
    raw = R.sentence_blocks(n); i = 0
    while i < len(raw):
        b = raw[i]
        if b in TRIPLE_BYTE: i += 3
        elif b in DOUBLE_BYTE: i += 2
        elif b == 0x00: i += 1
        elif b < 0x80: used.add(b); i += 1
        else: used.add((b << 8) + raw[i+1]); i += 2
free_blocks = iter(b for b in range(0x20, 0x80) if b not in used)

# 4) 字形码 c（从 0x10 起，避开 0x0E/0x0F/0xFE）+ 8×8 字模（bank128 tile[c]，下格）
codes = {}
_pool = iter(c for c in range(0x10, 0x100) if c not in (0x0E, 0x0F, 0xFE))
def code_for(ch):
    if ch not in codes:
        c = codes[ch] = next(_pool)
        rom[dst+c*16 : dst+c*16+16] = glyph8x8(ch)
    return codes[ch]

# 5) 一段一块（≤31 码位/块）：段串写空闲区 → text 反解 → 空单字节块；
#    块串 = 块 + 02(折行锚) + 块 + … + 句尾 05 82 00
p = FREE
bs = bytearray()
for k, seg in enumerate(SEGS):
    if k: bs += bytes([0x02])
    seq = bytes(code_for(ch) for ch in seg)
    rom[p:p+len(seq)] = seq
    t3 = solve_text(p, len(seq)); p += len(seq)
    blk = next(free_blocks)
    rom[R.text_pointer(blk):R.text_pointer(blk)+3] = t3
    bs += bytes([blk])
bs += bytes([0x05, 0x82, 0x00])
bsaddr = p; rom[bsaddr:bsaddr+len(bs)] = bs; p += len(bs)
s3 = solve_sentence(bsaddr)
assert s3, f"块串地址 {bsaddr:X} 不可达"
rom[R.sentence_pointer(62):R.sentence_pointer(62)+3] = s3

open(OUT, "wb").write(rom)
print(f"{OUT}: {len(rom)} bytes; 仅 B命门 NMI→{rom[NMI_PATCH:NMI_PATCH+3].hex()}（零 emit 改动）")
print(f"{len(codes)} 字, 字形码 c={min(codes.values()):#x}..{max(codes.values()):#x} (1 tile/字); 块串@{bsaddr:X} s3={s3.hex()}")
