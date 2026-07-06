#!/usr/bin/env python3
"""第一章·多 bank 版：每个背景场景(CG bank $0450)的字装进独立字库 bank，实机按场景切换。

突破点（asm 单点等长改，绕开 bank63 无空间）：NMI 里 $EB7F 进来时 A 已 = $0450(背景CG bank)，
故把 `LDA $0451; STA $045F`(AD5104 8D5F04) 改成 `ORA #$80; STA $045F; NOP`(0980 8D5F04 EA)——
对话框字库 bank = $0450 | 0x80。每个 CG 场景自动映射到扩 CHR 的 (cg|0x80) bank，无需查表/新代码。

装箱粒度 = 场景（用户指出对话框滚动、多句同屏，同场景句子必须同 bank；实测每场景 < 213 字）。
句→场景映射来自 mesen_ch1_playthrough.lua 的 trace（preview/playthrough*.log 的 SEQ 行）。
名字字用固定码位（名字块跨场景共享 block，码必须在所有 bank 指向同一字）。
"""
import re
from collections import defaultdict
from reinsert_full import glyph8x8, ICON_REUSE
from msgtool import Rom, iter_blocks, decode_ppu, DOUBLE_BYTE, TRIPLE_BYTE

SRC = "Metal Slader Glory (Japan).nes"; OUT = "MSG-zh-demo.nes"
CHR0 = 0x10 + 512 * 1024
NMI2 = 0x7EB8F                      # NMI region-1 字库bank：LDA$0451;STA$045F → ORA#$80;STA$045F;NOP
SAFE = (0x73604, 0x76000)
STRUCT_ZH = "translation/ch1/structured_zh.tsv"
TRACE_LOGS = ("reversing/ch1_scene_map.tsv", "preview/playthrough.log", "preview/playthrough_orig.log")

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
GAP_RE = re.compile(r"\{g([0-9A-Fa-f]{2})\}")
ICON_RE = re.compile("|".join(re.escape(k) for k in sorted(ICON_REUSE, key=len, reverse=True)))
UI_TILES = {0x17}
CODE_POOL = [c for c in list(range(0x10, 0xD0)) + list(range(0xE0, 0xFE))
             if c not in ICON_REUSE.values() and c not in PUNCT_REUSE.values() and c not in UI_TILES]


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


def load_scene_map():
    sm = {}
    for fn in TRACE_LOGS:
        try:
            for l in open(fn):
                if l.startswith("SEQ"):
                    _, n, b = l.split(); sm.setdefault(int(n), int(b, 16))
        except FileNotFoundError:
            pass
    return sm


def visible_chars(s):
    s = CTRL_RE.sub("", s); s = SETUP_RE.sub("", s); s = GAP_RE.sub("", s); s = ICON_RE.sub("", s)
    s = s.replace("/", "")
    return set(s) - set(PUNCT_REUSE)


tr = load_struct(STRUCT_ZH)
scene_map = load_scene_map()
rom = bytearray(open(SRC, "rb").read())
R0 = Rom(bytes(rom))
NAME_IDS = {b for b in iter_blocks()
            if (p := R0.block_ppu(b)) and len(p) >= 3 and p[0] == 0 and p[-1] == 0x11}

# 扩 CHR→1MB（256 个 4KB bank，容纳 cg|0x80 最大 0xE7=231）
rom[5] = 128; rom += bytes(512 * 1024)

# NMI 单点改：对话框字库 bank = $0450 | 0x80（替代原 B 命门硬编码 128）
assert rom[NMI2:NMI2 + 6] == bytes([0xAD, 0x51, 0x04, 0x8D, 0x5F, 0x04]), rom[NMI2:NMI2 + 6].hex()
rom[NMI2:NMI2 + 6] = bytes([0x09, 0x80, 0x8D, 0x5F, 0x04, 0xEA])   # ORA #$80; STA $045F; NOP

# 只回写「已知场景」的第一章句子；未测绘的留日文
include = [n for n in sorted(tr) if n in scene_map]
skipped = [n for n in tr if n not in scene_map]

# 名字字固定码位（所有场景 bank 一致；名字块共享 block）
name_chars = set()
for cn in JP2CN.values(): name_chars |= set(cn)
name_chars -= set(PUNCT_REUSE)
name_code = {ch: CODE_POOL[i] for i, ch in enumerate(sorted(name_chars))}
rest_pool = [c for c in CODE_POOL if c not in set(name_code.values())]

# 各场景字集 → 每场景独立 c2c + 字模写进 (cg|0x80) bank
scene_chars = defaultdict(set)
for n in include:
    scene_chars[scene_map[n]] |= (visible_chars(tr[n]) - set(PUNCT_REUSE) - name_chars)

scene_c2c = {}
for sc, chars in sorted(scene_chars.items()):
    fb = sc | 0x80
    rom[CHR0 + fb * 4096: CHR0 + fb * 4096 + 4096] = rom[CHR0:CHR0 + 4096]   # bank0 拷贝(边框/引号/图标/空白)
    srt = sorted(chars)
    assert len(name_code) + len(srt) <= len(CODE_POOL), f"场景${sc:02X}: {len(name_code)+len(srt)}字 > {len(CODE_POOL)}"
    c2c = dict(PUNCT_REUSE); c2c.update(name_code)
    for code, ch in zip(rest_pool, srt): c2c[ch] = code
    for ch, code in c2c.items():
        if ch in PUNCT_REUSE: continue
        rom[CHR0 + fb * 4096 + code * 16: CHR0 + fb * 4096 + code * 16 + 16] = glyph8x8(ch)
    scene_c2c[sc] = c2c
    print(f"场景 ${sc:02X}→字库bank ${fb:02X}: {len(srt)}场景字+{len(name_code)}名字字")

# 绿字(句63, 场景 $67)是顶部 overlay，光栅分屏读 bank 0——把该场景字模也拷进 bank 0
if 0x67 in scene_c2c:
    for ch, code in scene_c2c[0x67].items():
        if ch in PUNCT_REUSE: continue
        rom[CHR0 + code * 16: CHR0 + code * 16 + 16] = glyph8x8(ch)

# 名字块中文化（保 [00,X] 结构与前导空格；名字字用固定码，跨场景一致）
for bid in NAME_IDS:
    ppu = list(R0.block_ppu(bid)); X = ppu[1]
    cn = JP2CN.get(decode_ppu(bytes(ppu[2:-1])).strip())
    if not cn or any(c not in name_code for c in cn): continue
    content = ppu[2:]; lead = 0
    while lead < len(content) and content[lead] == 0xFE: lead += 1
    codes = [name_code[c] for c in cn]
    pad = X - lead - len(codes) - 1
    if pad < 0: continue
    sp, _ = R0.string_pointer(R0.read3(R0.text_pointer(bid)))
    rom[sp:sp + X + 2] = bytes([0x00, X] + [0xFE] * lead + codes + [0xFE] * pad + [0x11])

# char block 池（避开名字块/结构块/控制/折行/引号 ID）——block 全局共享，渲染按激活 bank 取 tile
STRUCT_IDS = {b for b in range(0x20, 0x80) if (p := R0.block_ppu(b)) and p[0] == 0}
RESERVED = NAME_IDS | STRUCT_IDS | {0x00, 0x02, 0x08, 0x09} | set(range(0x01, 0x20))
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


def orig_leading_gap(n):
    s = R0.sentence_blocks(n); i = 0
    while i < len(s):
        b = s[i]
        if b in TRIPLE_BYTE: i += 3; continue
        if b in DOUBLE_BYTE: i += 2; continue
        if b == 0x00: break
        blk = b if b < 0x80 else (b << 8) | s[i + 1]
        i += 1 if b < 0x80 else 2
        pp = R0.block_ppu(blk)
        if pp == b"\x00\x00": continue
        if len(pp) >= 3 and pp[0] == 0 and all(x == 0xFE for x in pp[2:]): return blk, pp[1]
        return None
    return None


done = 0
for n in include:
    text = tr[n]; c2c = scene_c2c[scene_map[n]]; bs = bytearray(); i = 0
    gap = orig_leading_gap(n); gap_pending = True
    while i < len(text):
        if gap_pending and text[i] in (" ", "　"):
            j = i
            while j < len(text) and text[j] in (" ", "　"): j += 1
            if gap and gap[1] == j - i:
                bs.append(gap[0]); i = j; gap_pending = False; continue
            gap_pending = False
        elif text[i] not in "{~/" and not SPK_RE.match(text, i):
            gap_pending = False
        m = CTRL_RE.match(text, i)
        if m: bs += bytes.fromhex(m.group(1)); i = m.end(); continue
        m = SETUP_RE.match(text, i)
        if m: bs.append(int(m.group(1), 16)); i = m.end(); continue
        m = GAP_RE.match(text, i)
        if m: bs.append(int(m.group(1), 16)); i = m.end(); continue
        if text[i] == "/": bs.append(0x02); i += 1; continue
        m = SPK_RE.match(text, i)
        if m: bs.append(SPEAKER_BLOCK[m.group(1)]); i = m.end(); continue
        m = ICON_RE.match(text, i)
        if m: emit_code(bs, ICON_REUSE[m.group(0)]); i = m.end(); continue
        ch = text[i]; i += 1
        if ch == "」": bs.append(0x09)
        elif ch in ("　", " "): emit_code(bs, c2c.get(ch) or 0xFE)
        else: emit_code(bs, c2c[ch])
    bs.append(0x00)
    assert p + len(bs) <= SAFE[1], f"安全区溢出 @句{n}"
    addr = p; rom[addr:addr + len(bs)] = bs; p += len(bs)
    s3 = solve_sentence(addr); assert s3, f"句{n}块串不可达"
    rom[R0.sentence_pointer(n):R0.sentence_pointer(n) + 3] = s3
    done += 1

open(OUT, "wb").write(rom)
a = open(SRC, "rb").read()
ok = all(a[lo:hi] == rom[lo:hi] for lo, hi in [(0x7FFF0, 0x80010), (0x76300, 0x76400), (0x7C000, 0x7E000)])
print(f"\n{OUT}: 回写 {done} 句（{len(scene_c2c)} 场景bank）；安全区用 {p - SAFE[0]}/{SAFE[1] - SAFE[0]}；代码完好 {ok}")
print(f"跳过(未测绘场景,留日文): {skipped}")
