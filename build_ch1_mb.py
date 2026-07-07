#!/usr/bin/env python3
"""第一章·多 bank 版：每个背景场景(CG bank $0450)的字装进独立字库 bank，实机按场景切换。

突破点（asm 单点等长改，绕开 bank63 无空间）：NMI 里 $EB7F 进来时 A 已 = $0450(背景CG bank)，
故把 `LDA $0451; STA $045F`(AD5104 8D5F04) 改成 `ORA #$80; STA $045F; NOP`(0980 8D5F04 EA)——
对话框字库 bank = $0450 | 0x80。每个 CG 场景自动映射到扩 CHR 的 (cg|0x80) bank，无需查表/新代码。

装箱粒度 = 场景（用户指出对话框滚动、多句同屏，同场景句子必须同 bank；实测每场景 < 213 字）。
句→场景映射来自 mesen_ch1_playthrough.lua 的 trace（preview/playthrough*.log 的 SEQ 行）。
名字字用固定码位（名字块跨场景共享 block，码必须在所有 bank 指向同一字）。
"""
import os
import sys
# 确定性构建:set 迭代受哈希随机化影响会导致每次输出字节不同(仅字→码分配变,不影响正确性,
# 但不可复现)。固定 PYTHONHASHSEED 后重执行一次,保证同源可复现。
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable] + sys.argv)
import re
from collections import defaultdict
from reinsert_full import glyph8x8, ICON_REUSE
from msgtool import Rom, iter_blocks, decode_ppu, DOUBLE_BYTE, TRIPLE_BYTE, CHARSET

# 原版假名 → 原始 tile 码。用于在中文译文里保留原版假名(密语 "えりな もう おきなよ" 必须保假名,
# 否则玩家学到中文却要在假名格里输入→存档功能废)。假名码从 CODE_POOL 保留(不派给中文)→各场景
# bank(=bank0 拷贝) 那些码位保原版假名字模;编码时假名字直接走原码。
KANA2CODE = {}
for _c, _ch in enumerate(CHARSET):
    if len(_ch) == 1 and ("぀" <= _ch <= "ヿ"):   # 平假名 + 片假名
        KANA2CODE.setdefault(_ch, _c)

SRC = "Metal Slader Glory (Japan).nes"; OUT = os.environ.get("OUT", "MSG-zh-demo.nes")
CHR0 = 0x10 + 0x100000              # CHR 起始（PRG 也扩到 1MB 后，CHR 挪到 0x100010）
NMI2 = 0x7EB8F                      # NMI region-1 字库bank：LDA$0451;STA$045F → ORA#$80;STA$045F;NOP
NMI_R2 = 0x7EB95                    # NMI region-2 bank($EB85 LDA$0452;STA$0460)：改成 LDA#GREEN_BANK
GREEN_BANK = 0xE0                   # 绿字(场景67 顶部 region2)专用 CHR bank(空闲)=bank0完整拷贝+句63中文
                                    # ★绿字读 region2($0460=$0452=0=bank0),与场景00(CONTINUE/存档)抢bank0→乱码。
                                    # 把 region2 重定向到 0xE0,bank0 保原版假名→存档屏干净,绿字照样中文。
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
UI_TILES = {0x17, 0x84, 0x9F, 0xAB, 0xDF, 0xEF, 0xFC, 0xFD}  # 0x17大括号 + 说话人小头像框复用的tile码(0x84/9F/AB/DF/EF/FC/FD,原版是假名形当框图案/框主体填充,中文不用假名故保留;0xFD是框主填充x41,曾误当padding漏排)
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
# 保留译文里出现的原版假名 tile 码(密语等)——不派给中文,使各 bank 该码位保原版假名字模。
KANA_CODES = {KANA2CODE[ch] for s in tr.values() for ch in s if ch in KANA2CODE}
CODE_POOL = [c for c in CODE_POOL if c not in KANA_CODES]
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

# ★绿字重定向(Phase 2 已解):绿字=场景67 顶部 strip,其 bank 来自 $0452(经 $EB58 `LDA $0450,X` X=2),
# 恒=0=bank0,与场景00 密语屏抢 bank0→乱码。实测 region2($0452/$0460)全程为0、仅场景67 在顶部渲染,
# 故改 NMI $EB85 `LDA $0452; STA $0460`(region2 shadow 拷贝,region2 全未用)→ `LDA #GREEN_BANK; STA $0452; NOP`:
# 每帧把 $0452 置 GREEN_BANK,下帧 $EB58(X=2,仅场景67)读到→绿字读 GREEN_BANK(=bank0拷贝+句63中文)。
# 其他场景 X=0 读 $0450 不受影响;bank0 保原版假名→密语屏干净。绿字与场景00 从此各用各的 bank。
assert rom[NMI_R2:NMI_R2 + 6] == bytes([0xAD, 0x52, 0x04, 0x8D, 0x60, 0x04]), rom[NMI_R2:NMI_R2 + 6].hex()
rom[NMI_R2:NMI_R2 + 6] = bytes([0xA9, GREEN_BANK, 0x8D, 0x52, 0x04, 0xEA])   # LDA #GREEN_BANK; STA $0452; NOP

# 场景分组装箱：CG 切换/紧密相邻的场景合并成组，组内所有 bank 共享同一字集+码位——跨 CG 或跨
# 场景显示的句在组内任何 bank 都有字、码位一致。开场组{0A,30,67}(机甲/通电/异变CG互切)、
# 海边区{0B,10,11}(海边/店门口/店铺反复切)；其余场景各自单组。名字字用全局固定码(名字块跨组
# 共享 block，码必须处处一致)。**只回写主线 59-172**：回访句(173+)与主线同 $0450 会挤进同 bank
# 累计超 213，暂留日文(需 asm 加维度区分同场景多访问才能上，见 REVERSING)。
SCENE_GROUPS = [{0x0A,0x30,0x67}, {0x0B,0x10,0x11}]   # 开场CG互切组 + 海边区(海边0B/店门口10/店铺11反复切)共享字集;0x17查米近景单独成组(114/115跨11↔17靠cross全局)
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
# 跨场景句(须全局固定码,各bank同码位)。★架构升级:只把"人工确认的cross候选"里【真跨>1场景组】的
# 保留为全局;组内跨(店内0x11↔查米近景0x17、海边0B↔店门口10↔店铺11)靠组内共享c2c→大幅腾出全局容量。
# (不从全地图找cross:穷尽探索会让深话题句在多场景出现被误判,撑爆码池。)
sent_scenes = defaultdict(set)
try:
    for _l in open("reversing/ch1_scene_samples.tsv"):
        _p = _l.split()
        if len(_p) >= 3 and _p[0] == "N": sent_scenes[int(_p[1])].add(int(_p[2], 16))
except FileNotFoundError:
    pass
# 只把【主线≤216】跨>1场景组的句设为全局cross(它们被改写→须各bank同码位)。
# 深话题>216不改写(range外)故不flag——避免穷尽探索的多场景误判撑爆码池。
cross_sents = {n for n, scs in sent_scenes.items() if n <= 216 and len({group_of(s) for s in scs}) > 1}
cross_sents |= {94, 97}  # 安全floor

name_chars = set()
for cn in JP2CN.values(): name_chars |= set(cn)
name_chars -= set(PUNCT_REUSE)
cross_chars = set()
for n in cross_sents:
    if n in tr: cross_chars |= (visible_chars(tr[n]) - set(PUNCT_REUSE) - name_chars)
CMD_CHARS = set("查看交谈回头休息前往")  # 通用命令名的字,每场景字库必有(修0E"交谈"→"P谈"、14命令乱);过多会挤掉句子,精确命令待逐一确认
cross_chars |= CMD_CHARS  # 并入跨场景字→每场景c2c都含(第208行)+字模注入每bank(第214行),修0E"交谈"→"P谈"、14"兴音省默"
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
    # ★场景00(CONTINUE/存档/密语系统屏)的句绝不改写:它用 bank0 原版假名字库渲染,且密语=假名输入,
    #   翻成中文会毁掉存档功能。保持原版日文(句15/17/19/20 等 gui_scene==0x00 的句)。
    if gui_scene.get(n) == 0x00: continue
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
    if os.environ.get("DIAG"):   # 诊断:全部显示句(主线+回访)的需求 vs 容量→溢出量+溢出字
        full = set()
        for n in mainline + revisit: full |= (visible_chars(tr[n]) - set(PUNCT_REUSE) - fixed_chars)
        dropped = [n for n in revisit if n not in keep]
        over = max(0, len(full) - avail_g)
        # 溢出字 = 全需求里"只被掉句用到"的字(减掉这些即可塞回)
        kept_chars = set()
        for n in keep: kept_chars |= (visible_chars(tr[n]) - set(PUNCT_REUSE) - fixed_chars)
        overflow_chars = full - kept_chars
        tag = '[' + ','.join('%02X' % s for s in sorted(g)) + ']'
        print(f"DIAG 组{tag}: 全需求{len(full)} 可用{avail_g} 溢出{over} 掉句{dropped} 溢出字({len(overflow_chars)}):{''.join(sorted(overflow_chars))}")
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

# ★ bank0 保持原版满字库不污染(修复场景00 密语/存档屏)。原 build 把整场景67(~104字)灌进 bank0
# 导致密语屏乱码,已删。绿字(句63 顶部 region)现回退为原版日文(读 bank0 原版假名)。
# Phase 2 备料:GREEN_BANK(0xE0)= bank0 完整拷贝 + 句63 中文;待解决绿字读 $0452 的重定向后启用。
gb = CHR0 + GREEN_BANK * 4096
rom[gb:gb + 4096] = rom[CHR0:CHR0 + 4096]
if 63 in tr and 0x67 in scene_c2c:
    for ch in visible_chars(tr[63]):
        code = scene_c2c[0x67].get(ch)
        if code is None or ch in PUNCT_REUSE: continue
        rom[gb + code * 16: gb + code * 16 + 16] = glyph8x8(ch)

# 名字块中文化：引擎左顶格渲染名字块(前导FE=隐形灰底空格,首字位置=块起始列+lead)。
# ★块宽X绝不改动(=原版=上一版汉化版,块字节数=X+2由X字节决定;一改X就出新排版问题)。
# 仅用前导空格 lead=1 让所有名字首字对齐到起始列+1(和忠一致),消除各自居中造成的阶梯。
for bid in NAME_IDS:
    ppu = list(R0.block_ppu(bid)); X = ppu[1]   # 保持原始块宽X → 换行/排版与原版完全一致
    cn = JP2CN.get(decode_ppu(bytes(ppu[2:-1])).strip())
    if not cn or any(c not in name_code for c in cn): continue
    codes = [name_code[c] for c in cn]; L = len(codes)
    if X < L + 2: continue        # 至少放得下 1前导+名+「,否则跳过保留原名字块
    lead = 1; trail = X - L - lead - 1   # 首字统一在起始列+1对齐;尾部空位补到「(块宽不变)
    sp, _ = R0.string_pointer(R0.read3(R0.text_pointer(bid)))
    rom[sp:sp + X + 2] = bytes([0x00, X] + [0xFE] * lead + codes + [0xFE] * trail + [0x11])

# 系统屏(场景00:CONTINUE 密语输入 / 存档)的句子不改写(保原版日文),但它们引用的 block 绝不能被
# block_for 重分配给中文字——否则原版假名 block 的 text_pointer 被顶掉→系统屏乱码(如句22 醒来独白)。
# 把这些句用到的 block 全部保留。SYS_SENTENCES=CONTINUE 独白(22)+存档流(15/17/19/20)+实测场景00 采样句。
SYS_SENTENCES = {15, 17, 19, 20, 22, 293, 364, 436, 441, 708, 762, 1165, 1322, 1379, 1519, 1528}
def _sent_block_ids(n):
    s = R0.sentence_blocks(n); i = 0; ids = set()
    while i < len(s):
        b = s[i]
        if b in TRIPLE_BYTE: i += 3; continue
        if b in DOUBLE_BYTE: i += 2; continue
        if b == 0x00: break
        ids.add(b if b < 0x80 else (b << 8) | s[i + 1]); i += 1 if b < 0x80 else 2
    return ids
SYS_BLOCKS = set()
for _n in SYS_SENTENCES:
    try: SYS_BLOCKS |= _sent_block_ids(_n)
    except Exception: pass

# char block 池（避开名字块/结构块/控制/折行/引号 ID + 系统屏句 block）——block 全局共享，渲染按激活 bank 取 tile
STRUCT_IDS = {b for b in range(0x20, 0x80) if (p := R0.block_ppu(b)) and p[0] == 0}
RESERVED = NAME_IDS | STRUCT_IDS | SYS_BLOCKS | {0x00, 0x02, 0x08, 0x09} | set(range(0x01, 0x20))
free_blocks = iter([b for b in range(0x20, 0x80) if b not in RESERVED]
                   + [b for b in range(0x8080, 0x8B54) if b not in SYS_BLOCKS])
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
        elif ch in KANA2CODE: emit_code(bs, KANA2CODE[ch])   # 原版假名(密语等)走原始 tile 码
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
