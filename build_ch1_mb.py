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
CHR0 = 0x10 + 0x100000              # CHR 起始（PRG 也扩到 1MB 后，CHR 挪到 0x100010）
NMI2 = 0x7EB8F                      # NMI region-1 字库bank：LDA$0451;STA$045F → ORA#$80;STA$045F;NOP
# 空闲区（与 reinsert_full 一致，勿撞 0x74000-0x75B00 的 bank58 立绘/头像指针表！）：
# text 串(每 block 1 字节，量小)放 0x73604-0x74000 真空闲区；句子 block 流放扩 PRG(0x76000+)。
TEXT_FREE = (0x73604, 0x74000)      # block 的 1 字节 text 串（string_pointer 可达，避开立绘数据）
BLK_FREE = (0x80010, 0x100010)      # 句子 block 流（★真·新增扩 PRG 区；0x76000-0x80010 是存活代码/数据，勿用）
STRUCT_ZH = "translation/struct_full.tsv"   # 全量结构化译文(含回访 173-216)
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
CODE_POOL = [c for c in list(range(0x2A, 0xD0)) + list(range(0xE0, 0xFE))
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


def load_scenes():
    """句 → 它显示期间出现过的所有 $0450 场景(集合)。preview/accurate.log(每帧采样，准确记录
    跨 CG 句的多场景)优先；其余句用 ch1_scene_map/playthrough 的首次 $0450(单场景)补。"""
    scenes = {}
    try:
        for l in open("preview/accurate.log"):
            if l.startswith("MAP"):
                _, n, bs = l.strip().split("\t")
                scenes[int(n)] = set(int(b, 16) for b in bs.split(","))
    except FileNotFoundError:
        pass
    for fn in TRACE_LOGS:
        try:
            for l in open(fn):
                if l.startswith("SEQ"):
                    _, n, b = l.split(); n = int(n)
                    if n not in scenes: scenes[n] = {int(b, 16)}
        except FileNotFoundError:
            pass
    return scenes


def visible_chars(s):
    s = CTRL_RE.sub("", s); s = SETUP_RE.sub("", s); s = GAP_RE.sub("", s); s = ICON_RE.sub("", s)
    s = s.replace("/", "")
    return set(s) - set(PUNCT_REUSE)


tr = load_struct(STRUCT_ZH)
scene_map = load_scenes()
rom = bytearray(open(SRC, "rb").read())
R0 = Rom(bytes(rom))
NAME_IDS = {b for b in iter_blocks()
            if (p := R0.block_ppu(b)) and len(p) >= 3 and p[0] == 0 and p[-1] == 0x11}

# 扩 PRG→1MB(句子 block 流空间，避开原 PRG 尾的立绘数据) + CHR→1MB(字库)。
# 布局：[header][原PRG 512K][新PRG 512K][原CHR 512K][新CHR 512K]
# ★复位向量:上电时 MMC5 $5117=$FF→末 8KB bank(1MB 时=bank127)映射 $E000-$FFFF。
#   扩 PRG 后 bank127 是新增空区,复位向量会读到 0→崩。故把原 PRG 末 8KB(含向量+固定代码)
#   拷到新 PRG 末 8KB,使 bank127 有效。
rom[4] = 64; rom[5] = 128
_prg = bytearray(rom[0x10:0x10 + 0x80000]) + bytes(0x80000)
_prg[-0x2000:] = rom[0x10 + 0x80000 - 0x2000:0x10 + 0x80000]   # 新PRG末8KB = 原PRG末8KB(向量bank)
_chr = bytearray(rom[0x10 + 0x80000:0x10 + 0x100000]) + bytes(0x80000)
rom = bytearray(rom[:0x10]) + _prg + _chr

# NMI 单点改：对话框字库 bank = $0450 | 0x80（替代原 B 命门硬编码 128）
assert rom[NMI2:NMI2 + 6] == bytes([0xAD, 0x51, 0x04, 0x8D, 0x5F, 0x04]), rom[NMI2:NMI2 + 6].hex()
rom[NMI2:NMI2 + 6] = bytes([0x09, 0x80, 0x8D, 0x5F, 0x04, 0xEA])   # ORA #$80; STA $045F; NOP

# 场景分组装箱：CG 切换/紧密相邻的场景合并成组，组内所有 bank 共享同一字集+码位——跨 CG 或跨
# 场景显示的句在组内任何 bank 都有字、码位一致。开场组{0A,30,67}(机甲/通电/异变CG互切)、
# 海边区{0B,10,11}(海边/店门口/店铺反复切)；其余场景各自单组。名字字用全局固定码(名字块跨组
# 共享 block，码必须处处一致)。**只回写主线 59-172**：回访句(173+)与主线同 $0450 会挤进同 bank
# 累计超 213，暂留日文(需 asm 加维度区分同场景多访问才能上，见 REVERSING)。
SCENE_GROUPS = [{0x0A,0x30,0x67}, {0x0B,0x10,0x11}]   # 开场CG互切组 + 海边区(海边0B/店门口10/店铺11反复切,用户实测确认)共享字集
def group_of(sc):
    for g in SCENE_GROUPS:
        if sc in g: return frozenset(g)
    return frozenset({sc})

gui_scene = {}   # 首次 $0450(单值,全覆盖)用于分组
for l in open("reversing/ch1_scene_map.tsv"):
    if l.startswith("SEQ"):
        _, n, b = l.split(); gui_scene.setdefault(int(n), int(b, 16))
# 选项深入对话(自动序列/GUI采样都没选到→未测绘): 手动补场景。183/187=海边0B梓深入对话
# (183梓聊大海/哥哥, 187忠问梓记不记得爸爸),否则留日文乱码
for _n in (183, 187): gui_scene.setdefault(_n, 0x0B)  # 187父母对话/183梓聊大海(选项深入对话,未测绘);贪心装箱按空间取舍

# 跨场景句(在多个 $0450 下显示,字须全局固定码才能各 bank 同码位):accurate 每帧采样标记的多场景句
# + 手动补 accurate 因 lastN 滞后漏采的边界句(海边↔店门口↔店铺间反复切,用户实测句91等跨)
cross_sents = set()
try:
    for l in open("preview/accurate.log"):
        if l.startswith("MAP"):
            _, n, bs = l.strip().split("\t")
            if len(bs.split(",")) > 1: cross_sents.add(int(n))
except FileNotFoundError:
    pass
cross_sents |= {65,90,91,92,94,97,110,113,114,115,122,130,140,141}  # 跨场景句:海边/开场/查米店+短转场过场句(GUI全章采样)

name_chars = set()
for cn in JP2CN.values(): name_chars |= set(cn)
name_chars -= set(PUNCT_REUSE)
cross_chars = set()
for n in cross_sents:
    if n in tr: cross_chars |= (visible_chars(tr[n]) - set(PUNCT_REUSE) - name_chars)
fixed_chars = name_chars | cross_chars
fixed_code = dict(PUNCT_REUSE)
for code, ch in zip(CODE_POOL, sorted(fixed_chars)): fixed_code[ch] = code
name_code = fixed_code   # 名字块用(名字字在 fixed 里)
rest_pool = [c for c in CODE_POOL if c not in set(fixed_code.values())]
CAP = len(rest_pool)   # 每场景独有字预算(码池去固定码)

# 组含回访(173-216)后仍 ≤ 预算则回写全部(主线+回访)；超则只回写主线(59-172)，回访留日文
# (热点场景 0B海边/0E工作间/14穿梭机 主线+回访累计超 213，需 asm 加维度分第二 bank，见 REVERSING)
group_sents = defaultdict(list)
for n in sorted(tr):
    # 主线 59-156 + 回访 173-216;跳过 157-172(STAFF英文名单+到空间站的第二章句,含超长独白171,会把预算撑爆)
    if n in gui_scene and (n <= 156 or 173 <= n <= 216): group_sents[group_of(gui_scene[n])].append(n)
include = []
group_chars = defaultdict(set)
for g, sents in group_sents.items():
    used_n = set()
    for n in sents: used_n |= (visible_chars(tr[n]) & name_chars)
    avail_g = len(rest_pool) + (len(name_chars) - len(used_n))   # 名字优化后该组独有字预算
    # 贪心装箱:主线(59-156)必回写;回访(173-216)按剩余空间逐句加(而非全或无,最大化回访)
    mainline = [n for n in sents if n <= 156]
    revisit = [n for n in sents if n > 156]
    chars = set()
    for n in mainline: chars |= (visible_chars(tr[n]) - set(PUNCT_REUSE) - fixed_chars)
    keep = list(mainline)
    for n in revisit:
        nc = chars | (visible_chars(tr[n]) - set(PUNCT_REUSE) - fixed_chars)
        if len(nc) <= avail_g: keep.append(n); chars = nc
    for n in keep:
        include.append(n)
        group_chars[g] |= (visible_chars(tr[n]) - set(PUNCT_REUSE) - fixed_chars)
include.sort()
skipped = [n for n in tr if n not in include]

scene_c2c = {}
for g, chars in group_chars.items():
    # 名字优化:该组只装用到的名字,未用名字的固定码位释放给独有字(名字块仍用全局码,该组不显示的名字不占字模)
    used_names = set()
    for n in include:
        if group_of(gui_scene[n]) == g:
            used_names |= (visible_chars(tr[n]) & name_chars)
    unused_name_codes = [name_code[nm] for nm in name_chars if nm not in used_names]
    avail = rest_pool + unused_name_codes
    srt = sorted(chars)
    assert len(srt) <= len(avail), f"组{[f'${s:02X}' for s in sorted(g)]}: 独有{len(srt)} > 可用{len(avail)}"
    c2c = dict(PUNCT_REUSE)
    for ch in cross_chars: c2c[ch] = fixed_code[ch]        # 跨场景字:全局固定码
    for nm in used_names: c2c[nm] = name_code[nm]          # 用到的名字:全局固定码
    for code, ch in zip(avail, srt): c2c[ch] = code        # 独有字:剩余码 + 未用名字码位
    for sc in g:
        fb = sc | 0x80
        rom[CHR0 + fb * 4096: CHR0 + fb * 4096 + 4096] = rom[CHR0:CHR0 + 4096]   # bank0 拷贝
        for ch, code in c2c.items():
            if ch in PUNCT_REUSE: continue
            rom[CHR0 + fb * 4096 + code * 16: CHR0 + fb * 4096 + code * 16 + 16] = glyph8x8(ch)
        scene_c2c[sc] = c2c
    print(f"组 {[f'${s:02X}' for s in sorted(g)]}: 独有{len(srt)} 用到名字{len(used_names)} 可用{len(avail)}")

# 绿字(句63, 场景 $67)是顶部 overlay，光栅分屏读 bank 0——把该场景字模也拷进 bank 0
if 0x67 in scene_c2c:
    for ch, code in scene_c2c[0x67].items():
        if ch in PUNCT_REUSE: continue
        rom[CHR0 + code * 16: CHR0 + code * 16 + 16] = glyph8x8(ch)

# 名字块中文化（保 [00,X] 块宽；名字在块内**左对齐**lead=0——引擎按固定起始列渲染名字块，
# 各名字都从块起始列开始→左端对齐；原版忠有前导FE(缩进)、中文名短会参差，统一 lead=0 最整齐）
for bid in NAME_IDS:
    ppu = list(R0.block_ppu(bid)); X = ppu[1]
    cn = JP2CN.get(decode_ppu(bytes(ppu[2:-1])).strip())
    if not cn or any(c not in name_code for c in cn): continue
    codes = [name_code[c] for c in cn]
    pad = X - len(codes) - 1    # 名字左对齐(lead=0)在块起始列,尾部FE填充到「,各名字左端对齐
    if pad < 0: continue        # 中文名超长则跳过（保留原名字块）
    sp, _ = R0.string_pointer(R0.read3(R0.text_pointer(bid)))
    rom[sp:sp + X + 2] = bytes([0x00, X] + codes + [0xFE] * pad + [0x11])

# char block 池（避开名字块/结构块/控制/折行/引号 ID）——block 全局共享，渲染按激活 bank 取 tile
STRUCT_IDS = {b for b in range(0x20, 0x80) if (p := R0.block_ppu(b)) and p[0] == 0}
RESERVED = NAME_IDS | STRUCT_IDS | {0x00, 0x02, 0x08, 0x09} | set(range(0x01, 0x20))
free_blocks = iter([b for b in range(0x20, 0x80) if b not in RESERVED] + list(range(0x8080, 0x8B54)))
tp = TEXT_FREE[0]; bp = BLK_FREE[0]; blk_of = {}


def block_for(code):
    global tp
    if code not in blk_of:
        assert tp + 1 <= TEXT_FREE[1], "text 串区满(勿撞 0x74000 立绘数据)"
        rom[tp] = code; t3 = solve_text(tp, 1); tp += 1
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
    text = tr[n]; c2c = scene_c2c[gui_scene[n]]; bs = bytearray(); i = 0
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
    assert bp + len(bs) <= BLK_FREE[1], f"块串区溢出 @句{n}"
    addr = bp; rom[addr:addr + len(bs)] = bs; bp += len(bs)
    s3 = solve_sentence(addr); assert s3, f"句{n}块串不可达"
    rom[R0.sentence_pointer(n):R0.sentence_pointer(n) + 3] = s3
    done += 1

# 立绘/头像数据完好性:bank58 的 $A000 指针表(file 0x74010)绝不能被句子/text串覆盖
a = open(SRC, "rb").read()
assert rom[0x74000:0x75B00] == a[0x74000:0x75B00], "★立绘/头像数据被覆盖!"
open(OUT, "wb").write(rom)
ok = all(a[lo:hi] == rom[lo:hi] for lo, hi in [(0x7FFF0, 0x80010), (0x7C000, 0x7E000), (0x74000, 0x75B00)])
print(f"\n{OUT}: 回写 {done} 句（{len(scene_c2c)} 场景bank）；text串用 {tp - TEXT_FREE[0]}/{TEXT_FREE[1] - TEXT_FREE[0]}；句子用 {bp - BLK_FREE[0]}；立绘完好 {ok}")
print(f"跳过(未测绘场景,留日文): {skipped}")
