#!/usr/bin/env python3
"""第一章试点·忠实回写：消费结构化中文（显式折行/设置块/控制码），演出与原版一致。

与之前 build_opening_struct 的区别：折行和设置块**不再靠启发式猜**，而是读结构化译文里的
显式 token（`/` 折行、`{sHH}` 设置块），控制码 `~XXXX~` 原样保留在其位置。名字块中文化、
引号 tile 保留、块级结构保留，与已验证的做法一致。

输入 translation/ch1/structured_zh.tsv（句号\t结构化中文）。不扩 PRG、块串留安全区、只回写试点句。
"""
import re
from reinsert_full import glyph8x8, ICON_REUSE
from msgtool import Rom, iter_blocks, decode_ppu, DOUBLE_BYTE, TRIPLE_BYTE

SRC = "Metal Slader Glory (Japan).nes"; OUT = "MSG-zh-demo.nes"
CHR0 = 0x10 + 512 * 1024; NEWBANK = 128; NMI_PATCH = 0x7EB8F
SAFE = (0x73604, 0x76000)
STRUCT_ZH = "translation/ch1/structured_zh.tsv"

SPEAKER_BLOCK = {"忠": 0x20, "艾莉娜": 0x21, "梓": 0x22, "查米": 0x23, "阿源": 0x24,
                 "希尔琪奴": 0x25, "凯蒂": 0x26, "恩凯": 0x27, "弥生": 0x28,
                 "女服务员": 0x29, "吉夫": 0x2A, "小夜子": 0x2B}
SPK_RE = re.compile("(" + "|".join(sorted(SPEAKER_BLOCK, key=len, reverse=True)) + r")\s*「")
JP2CN = {"忠": "忠", "エリナ": "艾莉娜", "あずさ": "梓", "チャーミー": "查米", "ゲン": "阿源",
         "ゲ ン": "阿源", "シルキーヌ": "希尔琪奴", "キャティ": "凯蒂", "エンカイ": "恩凯",
         "やよい": "弥生", "ウェイトレス": "女服务员", "ジフ": "吉夫", "ジ フ": "吉夫", "小夜子": "小夜子"}
PUNCT_REUSE = {"「": 0x11, "」": 0x12}
CTRL_RE = re.compile(r"~([0-9A-Fa-f]{2,6})~")
SETUP_RE = re.compile(r"\{s([0-9A-Fa-f]{2})\}")
ICON_RE = re.compile("|".join(re.escape(k) for k in sorted(ICON_REUSE, key=len, reverse=True)))


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
        if b2 <= 255 and 0x30 <= X + 0x30 <= 0x7F: return bytes([X + 0x30, b2, b3])
    return None


def load_struct(path):
    tr = {}
    for l in open(path, encoding="utf-8"):
        l = l.rstrip("\n")
        if l.startswith("#") or "\t" not in l: continue
        ns, s = l.split("\t", 1)
        if ns.strip().isdigit(): tr[int(ns)] = s
    return tr


def visible_chars(s):
    """结构化串里需要字模的字符（去掉 ~XXXX~ / {sHH} / / / 图标 / 「」）。"""
    s = CTRL_RE.sub("", s); s = SETUP_RE.sub("", s); s = ICON_RE.sub("", s)
    s = s.replace("/", "")
    return set(s) - set(PUNCT_REUSE)


tr = load_struct(STRUCT_ZH)
rom = bytearray(open(SRC, "rb").read())
R0 = Rom(bytes(rom))
NAME_IDS = {b for b in iter_blocks()
            if (p := R0.block_ppu(b)) and len(p) >= 3 and p[0] == 0 and p[-1] == 0x11}

# 扩 CHR→1MB、bank128=bank0 拷贝、B 命门
rom[5] = 128; rom += bytes(512 * 1024)
dst = CHR0 + NEWBANK * 4096
rom[dst:dst + 4096] = rom[CHR0:CHR0 + 4096]
assert rom[NMI_PATCH:NMI_PATCH + 3] == bytes([0xAD, 0x51, 0x04])
rom[NMI_PATCH:NMI_PATCH + 3] = bytes([0xA9, NEWBANK, 0xEA])

# 字模码池（单 bank；全量需多 bank）
CODE_POOL = [c for c in list(range(0x10, 0xD0)) + list(range(0xE0, 0xFE))
             if c not in ICON_REUSE.values() and c not in PUNCT_REUSE.values()]
# 名字字必装；对话字逐句累加，超一个 bank 容量的句子跳过（留日文，全量再多 bank）
glyphs = set()
for cn in JP2CN.values(): glyphs |= set(cn)
glyphs -= set(PUNCT_REUSE)
include = set()
for n in sorted(tr):
    ng = (visible_chars(tr[n]) - set(PUNCT_REUSE)) - glyphs
    if len(glyphs) + len(ng) <= len(CODE_POOL):
        glyphs |= ng; include.add(n)
skipped = [n for n in tr if n not in include]
print(f"字模预算 {len(CODE_POOL)}；纳入 {len(include)}/{len(tr)} 句，跳过(留日文): {skipped}")
char2code = dict(PUNCT_REUSE)
for code, ch in zip(CODE_POOL, sorted(glyphs)):
    char2code[ch] = code
    rom[dst + code * 16: dst + code * 16 + 16] = glyph8x8(ch)

# 名字块中文化（保 [00,X] 结构与长度 X，且保留原版前导空格 → 名字定位/居中不变，如 忠 与 リ 对齐）
for bid in NAME_IDS:
    ppu = list(R0.block_ppu(bid)); X = ppu[1]
    cn = JP2CN.get(decode_ppu(bytes(ppu[2:-1])).strip())
    if not cn or any(c not in char2code for c in cn): continue
    content = ppu[2:]                                   # X 字节，末尾 0x11(「)
    lead = 0
    while lead < len(content) and content[lead] == 0xFE: lead += 1   # 原版前导空格数（定位）
    codes = [char2code[c] for c in cn]
    pad = X - lead - len(codes) - 1                     # 尾部补空格到 「
    if pad < 0: continue
    sp, _ = R0.string_pointer(R0.read3(R0.text_pointer(bid)))
    rom[sp:sp + X + 2] = bytes([0x00, X] + [0xFE] * lead + codes + [0xFE] * pad + [0x11])

# char block 池（避开名字块/控制/折行/引号 ID）
RESERVED = NAME_IDS | {0x00, 0x02, 0x08, 0x09} | set(range(0x01, 0x20))
free_blocks = iter([b for b in range(0x20, 0x80) if b not in RESERVED] + list(range(0x8080, 0x8B54)))
p = SAFE[0]; blk_of = {}
def block_for(code):
    global p
    if code not in blk_of:
        rom[p] = code; t3 = solve_text(p, 1); p += 1
        blk = next(free_blocks)
        rom[R0.text_pointer(blk):R0.text_pointer(blk) + 3] = t3
        blk_of[code] = blk
    return blk_of[code]

def emit_code(bs, code):
    blk = block_for(code)
    bs += bytes([blk]) if blk < 0x80 else bytes([blk >> 8, blk & 0xFF])

done = 0
for n in sorted(include):
    text = tr[n]; bs = bytearray(); i = 0
    while i < len(text):
        m = CTRL_RE.match(text, i)
        if m: bs += bytes.fromhex(m.group(1)); i = m.end(); continue
        m = SETUP_RE.match(text, i)
        if m: bs.append(int(m.group(1), 16)); i = m.end(); continue           # {sHH} 设置块
        if text[i] == "/": bs.append(0x02); i += 1; continue                  # 折行锚（显式）
        m = SPK_RE.match(text, i)
        if m: bs.append(SPEAKER_BLOCK[m.group(1)]); i = m.end(); continue      # 名字块
        m = ICON_RE.match(text, i)
        if m: emit_code(bs, ICON_REUSE[m.group(0)]); i = m.end(); continue
        ch = text[i]; i += 1
        if ch == "」": bs.append(0x09)                                         # 引号块
        elif ch in ("　", " "): emit_code(bs, char2code.get(ch) or 0xFE)  # 空格→空白 tile
        else: emit_code(bs, char2code[ch])
    bs.append(0x00)
    assert p + len(bs) <= SAFE[1], f"安全区溢出 @句{n}"
    addr = p; rom[addr:addr + len(bs)] = bs; p += len(bs)
    s3 = solve_sentence(addr); assert s3, f"句{n}块串不可达"
    rom[R0.sentence_pointer(n):R0.sentence_pointer(n) + 3] = s3
    done += 1

# 绿字区域用 bank 0（原字体库）渲染——把中文字库也拷进 bank 0，让绿字也显示中文（实验）
rom[CHR0:CHR0 + 4096] = rom[dst:dst + 4096]

open(OUT, "wb").write(rom)
a = open(SRC, "rb").read()
ok = all(a[lo:hi] == rom[lo:hi] for lo, hi in [(0x7FFF0, 0x80010), (0x76300, 0x76400), (0x7C000, 0x7E000)])
print(f"{OUT}: 回写 {done} 句（结构化·忠实）；{len(glyphs)} 唯一字；安全区用 {p - SAFE[0]}/{SAFE[1] - SAFE[0]}；代码完好 {ok}")
