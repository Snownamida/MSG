#!/usr/bin/env python3
"""16×16 清晰字 demo（尝试2）：整段重写 $F135-$F186 + 16×16 字模 + B 命门(bank128)。

尝试1败因：agent 反汇编清单与真实字节不符。本版基于亲手反汇编（见 REVERSING.md）。

emit 新逻辑：读字形码 c ($0469,Y) → base=c<<2 → 写 base..base+3 四槽到 $04A8,X（
左列上下+右列上下），X+=4、列 $1A +=2。字库 bank128 每字 4 tile 连排
[4c=TL,4c+1=BL,4c+2=TR,4c+3=BR]，其余 tile 从 bank0 整拷（保边框）。
"""
from PIL import Image, ImageDraw, ImageFont
from reinsert import solve_text
from msgtool import Rom, DOUBLE_BYTE, TRIPLE_BYTE

SRC = "Metal Slader Glory (Japan).nes"; OUT = "MSG-16x16.nes"
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
CHR0 = 0x10 + 512 * 1024; NEWBANK = 128
NMI_PATCH = 0x7EB8F; EMIT_AT = 0x7F145; FREE = 0x73604
# 分段=折行锚点（原句在自然断句处插空块 0x02，引擎按 30 列阈值折行）；
# 16×16 每字 2 列 → 每段 ≤15 字
SEGS = ["艾莉娜「这就是这次从阿源", "那儿买来的那台吗总觉得", "挺有意思的呢」"]

# emit 重写（尝试2，按真实反汇编）：原 $F135-$F186 共 82 字节整段替换。
# 真实结构：$F135 判模式一次 → 测量循环($14=$FF)/发射循环($14≥0)两条独立路径；
#   $12=解码串长度(=$0469[0])，数据从 $0469+1 起(Y=1)，$1A/$1B=16位列计数；
#   原发射循环每字符写 [浊点标记$27, 字形码] 两槽，X+=2。
# 新逻辑：测量每码位 +2 列；发射每字符写 [4c,4c+1,4c+2,4c+3] 四槽(左列上下+右列上下)，
#   X+=4、+2 列；浊点 0E/0F 逻辑删除（中文不用）。c≤63 保证 ASL×2 后 C=0，ADC#1 安全。
EMIT = bytes([
    0xA0,0x01,                  # F135 LDY #$01
    0xA5,0x14, 0x10,0x15,       # F137 LDA $14; BPL $F150(EMIT)
    # MEAS:
    0xC6,0x12, 0x10,0x03,       # F13B DEC $12; BPL $F142
    0x4C,0xD7,0xF0,             # F13F JMP $F0D7 (下一 block)
    0xE6,0x1A, 0xD0,0x02,       # F142 INC $1A; BNE $F148
    0xE6,0x1B,                  # F146 INC $1B
    0xE6,0x1A, 0xD0,0xEF,       # F148 INC $1A; BNE $F13B
    0xE6,0x1B, 0xD0,0xEB,       # F14C INC $1B; BNE $F13B
    # EMIT:
    0xA6,0x14,                  # F150 LDX $14
    0xC6,0x12, 0x10,0x05,       # F152 ELP: DEC $12; BPL $F15B
    0x86,0x14, 0x4C,0xD7,0xF0,  # F156 STX $14; JMP $F0D7
    0xB9,0x69,0x04, 0xC8,       # F15B LDA $0469,Y; INY
    0x0A, 0x0A,                 # F15F ASL; ASL  (A=4c, C=0)
    0x9D,0xA8,0x04, 0xE8,       # F161 STA $04A8,X; INX   (TL)
    0x69,0x01, 0x9D,0xA8,0x04, 0xE8,  # F165 ADC#1; STA; INX  (BL)
    0x69,0x01, 0x9D,0xA8,0x04, 0xE8,  # F16B ADC#1; STA; INX  (TR)
    0x69,0x01, 0x9D,0xA8,0x04, 0xE8,  # F171 ADC#1; STA; INX  (BR)
    0xE6,0x1A, 0xD0,0x02,       # F177 INC $1A; BNE $F17D
    0xE6,0x1B,                  # F17B INC $1B
    0xE6,0x1A, 0xD0,0xD1,       # F17D INC $1A; BNE $F152(ELP)
    0xE6,0x1B, 0xD0,0xCD,       # F181 INC $1B; BNE $F152
    0xEA,0xEA,                  # F185 NOP; NOP (补齐到 $F187)
])
assert len(EMIT) == 0x52
# 原码前 13 字节守卫（$F135: LDY#1; LDA$14; BPL; DEC$12; BPL; JMP $F0D7）
EMIT_ORIG = bytes([0xA0,0x01,0xA5,0x14,0x10,0x1B,0xC6,0x12,0x10,0x03,0x4C,0xD7,0xF0])

def glyph16(ch):
    S = 64; hi = Image.new("L", (S, S), 0); d = ImageDraw.Draw(hi)
    f = ImageFont.truetype(FONT, int(S * 0.95)); bb = d.textbbox((0, 0), ch, font=f)
    d.text(((S-(bb[2]-bb[0]))//2-bb[0], (S-(bb[3]-bb[1]))//2-bb[1]), ch, fill=255, font=f)
    sm = hi.resize((16, 16), Image.BILINEAR).point(lambda v: 1 if v > 55 else 0)
    def t(ox, oy):
        p1 = bytearray([0xFF] * 8)
        for r in range(8):
            for c in range(8):
                if sm.getpixel((ox+c, oy+r)): p1[r] &= 0xFF ^ (1 << (7-c))
        return bytes([0xFF]*8) + bytes(p1)
    return [t(0,0), t(0,8), t(8,0), t(8,8)]     # [TL,BL,TR,BR] = 4c,4c+1,4c+2,4c+3

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

# 1) 扩 CHR 到 1MB；bank128 = bank0 整拷（保留对话框边框/空白 tile），字模稍后覆盖
rom[5] = 128; rom += bytes(512 * 1024)
dst = CHR0 + NEWBANK * 4096
rom[dst:dst+4096] = rom[CHR0:CHR0+4096]

# 2) emit patch（整段重写 $F135-$F186）
assert rom[EMIT_AT:EMIT_AT+len(EMIT_ORIG)] == EMIT_ORIG, "原 emit 字节与预期不符"
rom[EMIT_AT:EMIT_AT+len(EMIT)] = EMIT

# 3) NMI patch：对话框 region-1 → bank128
assert rom[NMI_PATCH:NMI_PATCH+3] == bytes([0xAD, 0x51, 0x04])
rom[NMI_PATCH:NMI_PATCH+3] = bytes([0xA9, NEWBANK, 0xEA])

# 4) 真正空闲的 block 槽。教训两则：
#    - 尝试1硬编码 0x8080+ → 踩中引号等在用块，36 句串坏；
#    - 双字节 idx ≥ 0xB54 的 text 表槽 (0x3D5C+3*idx ≥ 0x5F58) 已越过表尾、
#      落在句 1108 块串上——表后紧跟句子数据，"空双字节槽"全是幻影。
#    → 只有 0x20-0x7F 未引用的单字节槽真正可用（25 个）。
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

# 5) 字形码 c(1..N) + 16×16 字模(bank128 tile[4c..4c+3])
codes = {}
def code_for(ch):
    if ch not in codes:
        c = codes[ch] = len(codes) + 1               # 避开 0
        for j, t in enumerate(glyph16(ch)):
            rom[dst+(4*c+j)*16 : dst+(4*c+j)*16+16] = t
    return codes[ch]

# 6) 一段一块（块 PPU 串最多 31 码位，段 ≤15 字随便装）：
#    段串写空闲区 → text 反解 → 空单字节块；块串 = 块+02(折行锚)+块+... + 句尾 05 82 00
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
print(f"{OUT}: {len(rom)} bytes; emit patch {len(EMIT)}B @{EMIT_AT:X}; NMI→{rom[NMI_PATCH:NMI_PATCH+3].hex()}")
print(f"{len(codes)} 个字符, 字形码 c=1..{len(codes)}; 块串@{bsaddr:X} s3={s3.hex()}")
