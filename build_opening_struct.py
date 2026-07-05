#!/usr/bin/env python3
"""开场 demo（结构保留·诊断版）：复用原版名字块原样字节 + 中文对话，测演出还原。

目的：判定颜色/缩进/打字机节奏是否由「名字块」驱动。做法——
- 说话人转折（译文里 名字+「）→ 发射原版对应名字块 ID（原样，名字仍显日文），保留其一切效果；
- 对话文字 → 每字共享 block（block ID 避开所有名字块/折行/引号）；
- 折行锚 0x02 只在句末标点 。！？ 后插（先保守，看引擎+名字块的自然表现）；
- 控制码 ~XXXX~ 原样保留。
若颜色/缩进/音效随名字块回来 → 下一步把名字块内容中文化即可。
"""
import re
from reinsert_full import tokenize, glyph8x8, ICON_REUSE, sentence_chars, load_translation
from msgtool import Rom, iter_blocks, decode_ppu, DOUBLE_BYTE, TRIPLE_BYTE

SRC = "Metal Slader Glory (Japan).nes"; OUT = "MSG-zh-demo.nes"
CHR0 = 0x10 + 512 * 1024; NEWBANK = 128
NMI_PATCH = 0x7EB8F
SAFE = (0x73604, 0x76000)
OPENING = range(55, 101)
FOLD_AFTER = set("。！？")

# 说话人（中文）→ 原版名字块 ID（复用原样字节，含颜色/长度/缩进效果）
SPEAKER_BLOCK = {
    "忠": 0x20, "艾莉娜": 0x21, "梓": 0x22, "查米": 0x23, "阿源": 0x24,
    "希尔琪奴": 0x25, "凯蒂": 0x26, "恩凯": 0x27, "弥生": 0x28,
    "女服务员": 0x29, "吉夫": 0x2A, "小夜子": 0x2B,
}
SPK_RE = re.compile("(" + "|".join(sorted(SPEAKER_BLOCK, key=len, reverse=True)) + r")\s*「")

R0 = Rom(open(SRC, "rb").read())
# 所有名字块 ID（复用/保护，不可当作 char block 借用）
NAME_IDS = set()
for b in iter_blocks():
    ppu = R0.block_ppu(b)
    if len(ppu) >= 3 and ppu[0] == 0x00 and ppu[-1] == 0x11:
        NAME_IDS.add(b)
RESERVED = NAME_IDS | {0x00, 0x02, 0x09} | set(range(0x01, 0x20))


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
rom[5] = 128; rom += bytes(512 * 1024)
dst = CHR0 + NEWBANK * 4096
rom[dst:dst + 4096] = rom[CHR0:CHR0 + 4096]
assert rom[NMI_PATCH:NMI_PATCH + 3] == bytes([0xAD, 0x51, 0x04])
rom[NMI_PATCH:NMI_PATCH + 3] = bytes([0xA9, NEWBANK, 0xEA])

# 日文名 → 中文名（名字块中文化，保留 [00,X] 与长度 X → 颜色/缩进不变）
JP2CN = {"忠": "忠", "エリナ": "艾莉娜", "あずさ": "梓", "チャーミー": "查米",
         "ゲン": "阿源", "ゲ ン": "阿源", "シルキーヌ": "希尔琪奴", "キャティ": "凯蒂",
         "エンカイ": "恩凯", "やよい": "弥生", "ウェイトレス": "女服务员",
         "ジフ": "吉夫", "ジ フ": "吉夫", "小夜子": "小夜子"}

# 引号复用原版 tile（0x11=「 0x12=」，名字块/引号块都用它们，绝不能覆盖成中文）
PUNCT_REUSE = {"「": 0x11, "」": 0x12}

# 开场对话唯一字 + 所有中文名的字 → 码 + 字模（「」除外，复用原 tile）
glyphs = set()
for n in OPENING:
    if tr.get(n): glyphs |= sentence_chars(tr[n])
for cn in JP2CN.values(): glyphs |= set(cn)
glyphs -= set(PUNCT_REUSE)
CODE_POOL = [c for c in list(range(0x10, 0xD0)) + list(range(0xE0, 0xFE))
             if c not in ICON_REUSE.values() and c not in PUNCT_REUSE.values()]
assert len(glyphs) <= len(CODE_POOL)
char2code = dict(PUNCT_REUSE)          # 「」→原 tile（不写字模，保留原字形）
for code, ch in zip(CODE_POOL, sorted(glyphs)):
    char2code[ch] = code
    rom[dst + code * 16: dst + code * 16 + 16] = glyph8x8(ch)

# 名字块中文化：保留 [00,X] 前缀与长度 X（颜色/缩进/长度全不变），日文名换中文名
for bid in NAME_IDS:
    ppu = list(R0.block_ppu(bid)); X = ppu[1]
    jp = decode_ppu(bytes(ppu[2:-1])).strip()
    cn = JP2CN.get(jp)
    if not cn or any(c not in char2code for c in cn): continue   # 空名/图标块保持原样
    codes = [char2code[c] for c in cn]; pad = X - len(codes) - 1
    if pad < 0: continue                                          # 中文名太长放不下（demo 无）
    newppu = bytes([0x00, X] + codes + [0xFE] * pad + [0x11])
    assert len(newppu) == X + 2
    sp, _ = R0.string_pointer(R0.read3(R0.text_pointer(bid)))
    rom[sp:sp + len(newppu)] = newppu

# char block 池：避开所有名字块/控制/折行/引号 ID
p = SAFE[0]
free_blocks = iter([b for b in range(0x20, 0x80) if b not in RESERVED]
                   + list(range(0x8080, 0x8B54)))
blk_of = {}
def block_for(code):
    global p
    if code not in blk_of:
        rom[p] = code; t3 = solve_text(p, 1); p += 1
        blk = next(free_blocks)
        rom[R.text_pointer(blk):R.text_pointer(blk) + 3] = t3
        blk_of[code] = blk
    return blk_of[code]

def emit_char(bs, ch):
    code = ICON_REUSE.get(ch) or char2code[ch]
    blk = block_for(code)
    bs += bytes([blk]) if blk < 0x80 else bytes([blk >> 8, blk & 0xFF])

# 前导设置块：原版块串开头那些渲染空的低位设置块（区域/对话框初始化，如 03 / 06 04 01），
# 从拍平译文里看不见，必须从原版搬回。停在第一个控制码/名字块/文字/引号/折行。
SETUP_STOP = {0x00, 0x02, 0x08, 0x09, 0x0D, 0x0E} | DOUBLE_BYTE | TRIPLE_BYTE

def leading_setup(n):
    raw = R0.sentence_blocks(n); out = bytearray()
    for b in raw:
        if b in SETUP_STOP or b >= 0x1A or b in NAME_IDS: break
        out.append(b)
    return out

done = 0
for n in OPENING:
    if not tr.get(n): continue
    text = tr[n].lstrip("　 ")                 # 去行首多余空格（名字块自带定位）
    bs = bytearray(leading_setup(n))          # 保留原版前导设置块
    i = 0
    while i < len(text):
        # 控制码
        m = re.match(r"~([0-9A-Fa-f]{2,6})~", text[i:])
        if m:
            bs += bytes.fromhex(m.group(1)); i += m.end(); continue
        # 说话人 名字+「 → 原版名字块
        m = SPK_RE.match(text[i:])
        if m:
            bs += bytes([SPEAKER_BLOCK[m.group(1)]]); i += m.end(); continue
        # 图标 token（(爱心) 等）
        mi = re.match("|".join(re.escape(k) for k in sorted(ICON_REUSE, key=len, reverse=True)), text[i:])
        if mi:
            emit_char(bs, mi.group(0)); i += mi.end(); continue
        ch = text[i]; i += 1
        if ch == "」":
            bs += bytes([0x09])                 # 复用原版引号块
        else:
            emit_char(bs, ch)
            if ch in FOLD_AFTER: bs.append(0x02)
    bs.append(0x00)
    assert p + len(bs) <= SAFE[1], f"安全区溢出 @句{n}"
    addr = p; rom[addr:addr + len(bs)] = bs; p += len(bs)
    s3 = solve_sentence(addr)
    assert s3, f"句{n}块串 {addr:X} 不可达"
    rom[R.sentence_pointer(n):R.sentence_pointer(n) + 3] = s3
    done += 1

open(OUT, "wb").write(rom)
print(f"{OUT}: {len(rom)} bytes（PRG 未扩）")
print(f"回写开场 {done} 句；{len(glyphs)} 唯一字→bank128；复用 {len(NAME_IDS)} 个名字块；"
      f"安全区用 {p - SAFE[0]}/{SAFE[1] - SAFE[0]} 字节")
# 代码完好性
a = open(SRC, "rb").read()
ok = all(a[lo:hi] == rom[lo:hi] for lo, hi in
         [(0x7FFF0, 0x80010), (0x76300, 0x76400), (0x7C000, 0x7E000), (0x7F145, 0x7F190)])
print("关键代码区完好:", ok)
