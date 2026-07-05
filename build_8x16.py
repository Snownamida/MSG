#!/usr/bin/env python3
"""8×16 全高汉字（最小改法）：对话正文由 bank62 打字机 emit 渲染（非 $F135）。

尝试2 定位到真凶后的正解：保持 1 列/字（显现数组/列宽/字数计数全不动），
只把两条对话 emit 的「上格取 $27(FE)」改成「上格 = 字形码 c | 0x40」——
此时 A 恰为刚写过 $04A9 的 c，一条 ORA #$40 即可。于是：
  下格 tile = c（字下半 8×8），上格 tile = 0x40+c（字上半 8×8）→ 每列拼成 8×16 全高。
字号仍 8 宽（窄），但全高、每字两块专属 tile，比里程碑3 的 8×8 清晰得多，且零动状态机。

两条 emit（结构对称）：
  $D326 (file 0x7D336) 缓冲打字机：STA $04A9,X; PHA; LDA $27 → ORA #$40; STA $04A8,X
  $D9FC (file 0x7DA0C) 逐字即时  ：STA $04A9;   LDA $27 → ORA #$40; STA $04A8
不碰 $F135（那是名字/菜单排版，与对话正文无关）。
"""
from PIL import Image, ImageDraw, ImageFont
from reinsert import solve_text
from msgtool import Rom, DOUBLE_BYTE, TRIPLE_BYTE

SRC = "Metal Slader Glory (Japan).nes"; OUT = "MSG-8x16.nes"
# 缝合像素字体 8px：手工 hint，8×8 原生清晰（矢量字硬缩会糊）。OFL 授权，随仓库分发。
FONT = "fonts/fusion-pixel-8px-monospaced-zh_hans.otf"
CHR0 = 0x10 + 512 * 1024; NEWBANK = 128
NMI_PATCH = 0x7EB8F; FREE = 0x73604
# 两条对话 emit 的上格取值指令（A5 27 = LDA $27 → 09 40 = ORA #$40）
EMIT_MARK_1 = 0x7D336   # $D326 缓冲打字机
EMIT_MARK_2 = 0x7DA0C   # $D9FC 逐字即时
# 分段=折行锚点（原句自然断句插空块 0x02）
SEGS = ["艾莉娜「这就是这次从阿源", "那儿买来的那台吗总觉得", "挺有意思的呢」"]


_FONT = ImageFont.truetype(FONT, 8)   # 像素字体按设计 px 渲染


def glyph8x16(ch):
    """中文字 → (上半 tile, 下半 tile)，各 8×8。fusion-8px 原生 8×8，无抗锯齿；
    竖直居中放进 8×16 格（字占 cell 行 4..11），拆成上下两 tile。
    plane0 全 FF；plane1 笔画=位清零（黑底紫字，与原字库一致）。"""
    cell = Image.new("L", (8, 16), 0); d = ImageDraw.Draw(cell); d.fontmode = "1"
    bb = d.textbbox((0, 0), ch, font=_FONT)
    d.text(((8 - (bb[2] - bb[0])) // 2 - bb[0], 4), ch, fill=255, font=_FONT)  # y=4 居中
    def tile(oy):
        p1 = bytearray([0xFF] * 8)
        for r in range(8):
            for c in range(8):
                if cell.getpixel((c, oy + r)) > 127: p1[r] &= 0xFF ^ (1 << (7 - c))
        return bytes([0xFF] * 8) + bytes(p1)
    return tile(0), tile(8)     # (上半 → 0x40+c, 下半 → c)


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

# 2) 两条对话 emit patch：LDA $27 → ORA #$40（上格 = c|0x40）
for off in (EMIT_MARK_1, EMIT_MARK_2):
    assert rom[off:off+2] == bytes([0xA5, 0x27]), f"{off:X} 非 LDA $27"
    rom[off:off+2] = bytes([0x09, 0x40])

# 3) B 命门：对话框 region → bank128
assert rom[NMI_PATCH:NMI_PATCH+3] == bytes([0xAD, 0x51, 0x04])
rom[NMI_PATCH:NMI_PATCH+3] = bytes([0xA9, NEWBANK, 0xEA])

# 4) 真正空闲 block 槽（仅未引用的单字节 0x20-0x7F；双字节表尾 0x8B54 后是句1108 数据）
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

# 5) 字形码 c(1..N, ≤0x3F) + 8×16 双 tile（bank128 tile[c]=下半, tile[0x40+c]=上半）
codes = {}
def code_for(ch):
    if ch not in codes:
        c = codes[ch] = len(codes) + 1
        assert c <= 0x3F, "超过 63 字，c|0x40 会与上半 tile 冲突"
        top, bot = glyph8x16(ch)
        rom[dst+c*16 : dst+c*16+16] = bot
        rom[dst+(0x40+c)*16 : dst+(0x40+c)*16+16] = top
    return codes[ch]

# 6) 一段一块（≤31 码位/块）：段串写空闲区 → text 反解 → 空单字节块；
#    块串 = 块 + 02(折行锚) + 块 + … + 句尾 05 82 00，重定向到空闲区
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
print(f"{OUT}: {len(rom)} bytes; emit patch @{EMIT_MARK_1:X},{EMIT_MARK_2:X} → ORA #$40; NMI→{rom[NMI_PATCH:NMI_PATCH+3].hex()}")
print(f"{len(codes)} 字, 字形码 c=1..{len(codes)} (下半 tile[c], 上半 tile[0x40+c]); 块串@{bsaddr:X} s3={s3.hex()}")
