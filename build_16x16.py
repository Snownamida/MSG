#!/usr/bin/env python3
"""16×16 清晰字 demo：改 emit 循环让每字吐 4 tile + 16×16 字模 + B 命门(bank128)。

高风险：改 6502 汇编（emit 循环 $F135）。需实机验证，可能要调。

emit 新逻辑：读字形码 c ($0469,Y) → base=c<<2 → 写 base,base+1,base+2,base+3 到 $04A8,X；
游标 $14 +4、列 $1A +2。字库 bank128 每字 4 tile 连排 [4c=TL,4c+1=BL,4c+2=TR,4c+3=BR]。
"""
from PIL import Image, ImageDraw, ImageFont
from reinsert import solve_text
from msgtool import Rom

SRC = "Metal Slader Glory (Japan).nes"; OUT = "MSG-16x16.nes"
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
CHR0 = 0x10 + 512 * 1024; NEWBANK = 128
NMI_PATCH = 0x7EB8F; EMIT_AT = 0x7F145; FREE = 0x73604
TRANS = "艾莉娜「这就是这次从阿源那儿买来的那台吗总觉得挺有意思的呢」"

# emit 新循环（62 字节 ≤ 原 80）：BMI→MEAS(off49)、BPL→ELP(off8)、BPL→MEAS
EMIT = bytes([
    0xA5,0x14, 0x30,0x2D, 0xA6,0x14, 0xA0,0x01,            # LDA$14;BMI MEAS;LDX$14;LDY#1
    0xB9,0x69,0x04, 0xC8, 0x0A,0x0A,                        # ELP: LDA$0469,Y;INY;ASL;ASL
    0x9D,0xA8,0x04,0xE8, 0x69,0x01, 0x9D,0xA8,0x04,0xE8,    # STA$04A8,X;INX; ADC#1;STA;INX
    0x69,0x01, 0x9D,0xA8,0x04,0xE8, 0x69,0x01, 0x9D,0xA8,0x04,0xE8,  # x2 more tiles
    0xE6,0x1A, 0xE6,0x1A, 0xC6,0x12, 0x10,0xDC,             # INC$1A;INC$1A;DEC$12;BPL ELP
    0x86,0x14, 0x4C,0xD7,0xF0,                              # STX$14;JMP$F0D7
    0xE6,0x1A, 0xE6,0x1A, 0xC6,0x12, 0x10,0xF8, 0x4C,0xD7,0xF0,  # MEAS: +2列/字;JMP$F0D7
])
assert len(EMIT) == 60

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

# 1) 扩 CHR 到 1MB
rom[5] = 128; rom += bytes(512 * 1024)
dst = CHR0 + NEWBANK * 4096

# 2) emit patch（改 $F135 发射循环）
print("原 emit 前 16 字节:", rom[EMIT_AT:EMIT_AT+16].hex())
rom[EMIT_AT:EMIT_AT+len(EMIT)] = EMIT

# 3) NMI patch：对话框 region-1 → bank128
assert rom[NMI_PATCH:NMI_PATCH+3] == bytes([0xAD, 0x51, 0x04])
rom[NMI_PATCH:NMI_PATCH+3] = bytes([0xA9, NEWBANK, 0xEA])

# 4) 每字符 → 字形码 c(1..N) + 16×16 字模(bank128 tile[4c..4c+3]) + block + 单码位串
p = FREE; blk_i = 0; ch2blk = {}; codes = {}
def block_for(ch):
    global p, blk_i
    if ch not in ch2blk:
        c = codes.setdefault(ch, len(codes) + 1)     # 字形码 c=1..N（避开 0）
        for j, t in enumerate(glyph16(ch)):
            rom[dst+(4*c+j)*16 : dst+(4*c+j)*16+16] = t
        rom[p] = c; t3 = solve_text(p, 1); p += 1     # 单码位串 [c]
        blk = 0x8080 + blk_i; blk_i += 1
        rom[R.text_pointer(blk):R.text_pointer(blk)+3] = t3
        ch2blk[ch] = blk
    return ch2blk[ch]

# 5) 句 62 块串（每字符→block）重定向到空闲区
bs = bytearray()
for ch in TRANS:
    blk = block_for(ch)
    bs += bytes([blk >> 8, blk & 0xFF])
bs += b'\x00'
bsaddr = p; rom[bsaddr:bsaddr+len(bs)] = bs; p += len(bs)
s3 = solve_sentence(bsaddr)
assert s3, f"块串地址 {bsaddr:X} 不可达"
rom[R.sentence_pointer(62):R.sentence_pointer(62)+3] = s3

open(OUT, "wb").write(rom)
print(f"{OUT}: {len(rom)} bytes; emit patch {len(EMIT)}B @{EMIT_AT:X}; NMI→{rom[NMI_PATCH:NMI_PATCH+3].hex()}")
print(f"{len(codes)} 个字符, 字形码 c=1..{len(codes)}; 块串@{bsaddr:X} s3={s3.hex()}")
