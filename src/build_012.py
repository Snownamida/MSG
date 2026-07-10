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

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # src/x.py → 项目根
SRC = os.path.join(_ROOT, "roms", "Metal Slader Glory (Japan).nes")
OUT = os.environ.get("OUT", os.path.join(_ROOT, "roms", "MSG-zh-demo.nes"))
CHR0 = 0x10 + 0x100000              # CHR 起始（PRG 也扩到 1MB 后，CHR 挪到 0x100010）
NMI2 = 0x7EB8F                      # NMI region-1 字库bank：LDA$0451;STA$045F → ORA#$80;STA$045F;NOP
NMI_R2 = 0x7EB95                    # NMI region-2 bank($EB85 LDA$0452;STA$0460)：改成 LDA#GREEN_BANK
GREEN_BANK = 0x9A                   # 绿字(场景67 顶部 region2)专用 CHR bank。★012:原0xE0撞第二章场景60(60|0x80=E0),挪到0x9A(=1A|0x80,1A非场景→空闲)
                                    # ★绿字读 region2($0460=$0452=0=bank0),与场景00(CONTINUE/存档)抢bank0→乱码。
                                    # 把 region2 重定向到 0xE0,bank0 保原版假名→存档屏干净,绿字照样中文。
# ★硬骨头③:句级第二字库bank(ExRAM 钩子)。单场景bank装不下的溢出句(如187)放独立 B bank,运行时按句切换:
#   detour $F081(读句指针例程尾,此刻 $5115 仍=句子表bank可验表)`STA $5115`→`JSR $5FA5`(等长3B);
#   ExRAM $5FA5 例程:主表($A000首字节==0)时默认 shadow($5FFF)=$0450|0x80,$87/$88 命中 B-list→表项bank;
#   NMI $EB7F 改 `LDA $5FFF; STA $045F`(等长6B)。ExRAM $5FA5-$5FFF 实测全章(含密语屏00)零写入;
#   例程由 bank127(扩PRG启动副本,$5117 切走后永不执行=自由区)开机拷入 ExRAM($5104=2 仅reset设置)。
#   共显安全:实测选话题时对话框先清屏(菜单开着时框已空),深话题句独占屏幕,B bank 只需固定字+该句字。
B_SENTS = {187: 0xA1,                          # 海边深话题:梓聊父亲(情感戏)
           204: 0xA2, 205: 0xA2, 206: 0xA2, 207: 0xA2}   # 0E工作间深话题(阿源车库),共享一个B bank
# 句号→B bank(空闲 $A1 起;bank=bank0拷贝+固定/名字字全局码+该bank各句独有字)。
# ★只放"独占屏幕"的句(菜单深话题:选择时对话框先清屏);主线滚动句禁入(邻句共显会错bank)。
LUA_OFF = 1               # ★Lua trace N 标签 = msgtool 句号 −1;所有 Lua 采样数据键 +1 对齐 tr 空间
DETOUR = 0x7F091          # file: $F081 `STA $5115`(8D 15 51)
BANK127 = 0xFE010         # file: 扩PRG末8KB=bank63启动副本
# 空闲区（与 reinsert_full 一致，勿撞 0x74000-0x75B00 的 bank58 立绘/头像指针表！）：
# text 串(每 block 1 字节，量小)放 0x73604-0x74000 真空闲区；句子 block 流放扩 PRG(0x76000+)。
TEXT_FREE = (0x73604, 0x74000)      # block 的 1 字节 text 串（string_pointer 可达，避开立绘数据）
BLK_FREE = (0x80010, 0x100010)      # 句子 block 流（★真·新增扩 PRG 区；0x76000-0x80010 是存活代码/数据，勿用）
STRUCT_ZH = os.path.join(_ROOT, "translation", "struct_full.tsv")   # 全量结构化译文(含回访 173-216)
TRACE_LOGS = (os.path.join(_ROOT, "reversing", "data", "ch1_scene_map.tsv"),
              os.path.join(_ROOT, "preview", "playthrough.log"),
              os.path.join(_ROOT, "preview", "playthrough_orig.log"))

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
    跨 CG 句的多场景)优先；其余句用 ch1_scene_map/playthrough 的首次 $0450(单场景)补。
    ★LUA_OFF:trace 的 N 标签=(p-$BCB5)//3 是 0-based slot 号,= msgtool 句号 −1(表基 $BCB5
    即 msgtool 句1 的表项;实证 lastN=186 时屏显 tr[187])。所有 Lua 采样数据键 +1 对齐 tr 空间,
    否则 tr[n] 按"下一句的场景"装箱→场景边界句错 bank(实测 s137_0E/s141_13 等 17 处边界乱码)。"""
    scenes = {}
    try:
        for l in open(os.path.join(_ROOT, "preview", "accurate.log")):
            if l.startswith("MAP"):
                _, n, bs = l.strip().split("\t")
                scenes[int(n) + LUA_OFF] = set(int(b, 16) for b in bs.split(","))
    except FileNotFoundError:
        pass
    for fn in TRACE_LOGS:
        try:
            for l in open(fn):
                if l.startswith("SEQ"):
                    _, n, b = l.split(); n = int(n) + LUA_OFF
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

# NMI 单点改：对话框字库 bank = ExRAM shadow $5FFF（硬骨头③:默认 $0450|0x80,B句时=B bank;
# 替代上一版 `ORA #$80` 硬映射——shadow 由 $5FA5 例程按当前句维护）
assert rom[NMI2:NMI2 + 6] == bytes([0xAD, 0x51, 0x04, 0x8D, 0x5F, 0x04]), rom[NMI2:NMI2 + 6].hex()
rom[NMI2:NMI2 + 6] = bytes([0xAD, 0xFF, 0x5F, 0x8D, 0x5F, 0x04])   # LDA $5FFF; STA $045F

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

gui_scene = {}   # 首次 $0450(单值,全覆盖)用于分组;键 +LUA_OFF 对齐 tr 空间(见 load_scenes 注)
for l in open(os.path.join(_ROOT, "reversing", "data", "ch1_scene_map.tsv")):
    if l.startswith("SEQ"):
        _, n, b = l.split(); gui_scene.setdefault(int(n) + LUA_OFF, int(b, 16))
# 挖掘机测绘(穷尽话题):补充场景映射 + 超范围深挖句白名单(217<tr≤281 主表句走 A bank,
# 不装箱必乱码;>281 追加表句由深bank保底日文,无需强制)
DIG_EXTRA = set()
try:
    for l in open(os.path.join(_ROOT, "reversing", "data", "ch1_dig_scene.tsv")):
        p = l.split()
        if len(p) >= 2 and p[0].isdigit():
            n = int(p[0]) + LUA_OFF
            gui_scene.setdefault(n, int(p[1], 16))
            if 217 < n <= 281: DIG_EXTRA.add(n)
except FileNotFoundError:
    pass
# 选项深入对话(自动序列/GUI采样都没选到→未测绘): 手动补场景。183/187=海边0B梓深入对话
# (183梓聊大海/哥哥, 187忠问梓记不记得爸爸),否则留日文乱码
for _n in (183, 187): gui_scene.setdefault(_n, 0x0B)  # 187父母对话/183梓聊大海(选项深入对话,未测绘);贪心装箱按空间取舍

# ★012:第二章 句号→场景(seqrun stage_2 遍历产出;句号243-704,27场景)。
CH2_SENTS = set()
try:
    for _l in open(os.path.join(_ROOT, "reversing", "data", "ch2_scene_map.tsv")):
        _p = _l.split()
        if len(_p) >= 3 and _p[0] == "N" and _p[1].isdigit():
            _n = int(_p[1]); gui_scene.setdefault(_n, int(_p[2], 16)); CH2_SENTS.add(_n)
except FileNotFoundError:
    pass

# 跨场景句(在多个 $0450 下显示,字须全局固定码才能各 bank 同码位):accurate 每帧采样标记的多场景句
# + 手动补 accurate 因 lastN 滞后漏采的边界句(海边↔店门口↔店铺间反复切,用户实测句91等跨)
# 跨场景句(须全局固定码,各bank同码位)。★架构升级:只把"人工确认的cross候选"里【真跨>1场景组】的
# 保留为全局;组内跨(店内0x11↔查米近景0x17、海边0B↔店门口10↔店铺11)靠组内共享c2c→大幅腾出全局容量。
# (不从全地图找cross:穷尽探索会让深话题句在多场景出现被误判,撑爆码池。)
sent_scenes = defaultdict(set)
try:
    for _l in open(os.path.join(_ROOT, "reversing", "data", "ch1_scene_samples.tsv")):
        _p = _l.split()
        if len(_p) >= 3 and _p[0] == "N": sent_scenes[int(_p[1]) + LUA_OFF].add(int(_p[2], 16))
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
    # 主线 ≤157 + 回访 174-217(tr空间;原 Lua 标定 59-156/173-216 整体+1,见 LUA_OFF)
    # 跳过 158-173(STAFF英文名单+到空间站的第二章句,含超长独白,会把预算撑爆)
    # ★场景00(CONTINUE/存档/密语系统屏)的句绝不改写:它用 bank0 原版假名字库渲染,且密语=假名输入,
    #   翻成中文会毁掉存档功能。保持原版日文(gui_scene==0x00 的句)。
    if gui_scene.get(n) == 0x00: continue
    if n in B_SENTS: continue   # ★B句走独立第二bank(硬骨头③),不占场景组码池
    if n in gui_scene and (n <= 157 or 174 <= n <= 217 or n in DIG_EXTRA or n in CH2_SENTS): group_sents[group_of(gui_scene[n])].append(n)
include = []
group_chars = defaultdict(set)
group_kana_free = {}   # 组 → 可回收的假名码(该组候选句用不到的;全局假名保留只对需要的组生效)
_KANA_LIST = sorted(KANA_CODES)
for g, sents in group_sents.items():
    used_n = set()
    for n in sents: used_n |= (visible_chars(tr[n]) & name_chars)
    # ★假名码按组回收:KANA_CODES 全局从 CODE_POOL 保留是为密语(句154,仅场景14)——
    # 该组候选句用不到的假名码归还本组码池(bank=bank0拷贝,回收位注入中文字模,其余组不受影响)
    _gk = {KANA2CODE[ch] for n in sents for ch in tr[n] if ch in KANA2CODE}
    group_kana_free[g] = [c for c in _KANA_LIST if c not in _gk]
    avail_g = len(rest_pool) + (len(name_chars) - len(used_n)) + len(group_kana_free[g])   # 名字优化+假名回收后预算
    # 贪心装箱:主线(≤157)必回写;回访(174-217)按剩余空间逐句加(而非全或无,最大化回访)
    mainline = [n for n in sents if n <= 157]
    revisit = [n for n in sents if n > 157]
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
# ★012 Phase2 待办(溢出句→B bank):发现更深——第二章句多 >281,指针在 bank1 句表(_pf≥0x2010),
# 硬骨头③ B-list 仅支持 bank0(assert _pf<0x2010)。需先扩钩子支持 bank1/追加表三表分派 + 解决表放置
# (91B安全区仅够代码~85B,表须另置于可映射空闲区)。详见 docs/CH2_PACKING_PLAN.md。
skipped = [n for n in tr if n not in include and n not in B_SENTS]

scene_c2c = {}
for g, chars in group_chars.items():
    # 名字优化:该组只装用到的名字,未用名字的固定码位释放给独有字(名字块仍用全局码,该组不显示的名字不占字模)
    used_names = set()
    for n in include:
        if group_of(gui_scene[n]) == g:
            used_names |= (visible_chars(tr[n]) & name_chars)
    unused_name_codes = [name_code[nm] for nm in name_chars if nm not in used_names]
    avail = rest_pool + unused_name_codes + group_kana_free.get(g, [])
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

# ★硬骨头③:B句独立字库 bank + 专属 c2c。固定字/名字保全局码(与 A bank 同码位→切换瞬间共显安全),
# 同 bank 各句合并一套 c2c(共享码池;同bank句间共显也安全),独有字独占剩余码池。
b_c2c = {}
_bank_sents = defaultdict(list)
for _n, _bank in B_SENTS.items():
    if _n in tr: _bank_sents[_bank].append(_n)
for _bank, _ns in sorted(_bank_sents.items()):
    _used_names, _own = set(), set()
    for _n in _ns:
        _used_names |= (visible_chars(tr[_n]) & name_chars)
        _own |= (visible_chars(tr[_n]) - set(PUNCT_REUSE) - fixed_chars - name_chars)
    _own = sorted(_own)
    assert len(_own) <= len(rest_pool), f"B bank ${_bank:02X} 独有字{len(_own)}超单bank码池{len(rest_pool)}"
    _c = dict(PUNCT_REUSE)
    for ch in cross_chars: _c[ch] = fixed_code[ch]
    for nm in _used_names: _c[nm] = name_code[nm]
    for code, ch in zip(rest_pool, _own): _c[ch] = code
    rom[CHR0 + _bank * 4096: CHR0 + _bank * 4096 + 4096] = rom[CHR0:CHR0 + 4096]   # bank0 拷贝
    for ch, code in _c.items():
        if ch in PUNCT_REUSE: continue
        rom[CHR0 + _bank * 4096 + code * 16: CHR0 + _bank * 4096 + code * 16 + 16] = glyph8x8(ch)
    for _n in _ns: b_c2c[_n] = _c
    print(f"B bank ${_bank:02X}: 句{sorted(_ns)} 独有字{len(_own)} 名字{len(_used_names)}")

# ★深bank(hook v2 追加表默认 shadow=$0450|$C0):每个第一章场景放 bank0 完整拷贝→
# 未翻译深句(>281,追加表,出现在后进度回访/深挖态)显示为**干净原版日文**,取代先前透过
# 中文 A bank 的乱码(机制级保底,无需逐句测绘)。待测绘到具体深句后可叠加中文字模(同 B bank)。
# 冲突检查:sc|C0 可能撞在用 bank(0x67|C0=$E7 撞 scene67 A bank、0x5C|C0=$DC 撞 scene5C A bank),
# 撞则跳过(这些场景是过场/瞬态 CG,无深挖入口);$E0=GREEN 跳过。
_used_banks = {s | 0x80 for s in scene_c2c} | set(B_SENTS.values()) | {GREEN_BANK}
for _sc in sorted(set(gui_scene.values()) | {0x00, 0x0A, 0x30}):
    _db = (_sc | 0xC0) & 0xFF
    if _db in _used_banks: continue
    rom[CHR0 + _db * 4096: CHR0 + _db * 4096 + 4096] = rom[CHR0:CHR0 + 4096]

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

# ★012:钩子注入移到此处(分配之后)——B_SENTS 含第二章溢出句时钩子才完整
# ★硬骨头③ 三件套(设计见文件头 B_SENTS 注释;ExRAM 空隙/清屏行为均已实测验证):
# ② detour:$F081 `STA $5115`→`JSR $5FA5`。$F06F-$F084 = "经($87)读句指针3字节"核心例程(bank63),
#   每句显示必经;detour 点在恢复 $5115 之前,故例程内可用 $A000 首字节验"当前映射=主表bank0"。
assert rom[DETOUR:DETOUR + 3] == bytes([0x8D, 0x15, 0x51]), rom[DETOUR:DETOUR + 3].hex()
rom[DETOUR:DETOUR + 3] = bytes([0x20, 0xA5, 0x5F])   # JSR $5FA5
# ③ ExRAM payload v2(0x5B=91B → $5FA5-$5FFF,shadow@$5FFF):
#   · 追加表(sig=$36,$88<$BD)→ 深bank默认 shadow=$0450|$C0(每场景深句bank;>281 深句全走它,
#     未翻译/未装下的深句经"深bank=bank0拷贝"保底→显示干净原版日文,不再乱码)
#   · 主表(sig=$00,$88≥$BC)→ 默认 shadow=$0450|$80,再内联比较 B 块(B_SENTS 连续slot区段,
#     lo ±2容差:引擎显示期间以表项+1/+2偏移重读)
#   守卫依据(187显示中实测指针流):文本表读 sig36+$88≥$BD4C、其他表读 sig≠36 或 $88<$BC,
#   均被上述条件精确排除;寄存器契约:X/Y 不动,出口 LDA $7E 复刻原指令的 A 与 N/Z。
def _asm_hook_v2():
    # B_SENTS → 连续 slot 区段 [hi, loStart, span, bank]。span=3×句数:每 slot 表项恰 3 字节,
    # "±2容差"=表项内偏移(引擎以 +1/+2 重读),已含在 3 内——★勿再加 2,会罩进下一 slot
    # 误伤相邻句(tr[188]/tr[208] 曾因此被误路由 B bank)。
    runs = []
    for _n, _bk in sorted(B_SENTS.items()):
        _pf = R0.sentence_pointer(_n)
        assert _pf < 0x2010, f"B句{_n}不在主表bank0(追加表深句走深bank默认,无需挂B)"
        _pc = 0xA000 + _pf - 0x10   # 表项 CPU 地址——由 msgtool 直接换算,免 off-by-one
        if runs and runs[-1][3] == _bk and (_pc >> 8) == runs[-1][0] and (_pc & 0xFF) == runs[-1][1] + runs[-1][2]:
            runs[-1][2] += 3        # 与前项连续同bank → 并段
        else:
            assert (_pc & 0xFF) <= 0xF8, f"B句{_n}表项跨页"
            runs.append([_pc >> 8, _pc & 0xFF, 3, _bk])
    code = bytearray(); fix = []                    # fix: 待回填 done 的分支偏移位
    def _b(op): code.extend([op, 0x00]); fix.append(len(code) - 1)
    code += bytes([0xAD, 0x00, 0xA0])               # LDA $A000
    code += bytes([0xF0, 0x00]); _main = len(code) - 1   # BEQ main
    code += bytes([0xC9, 0x36]); _b(0xD0)           # CMP #$36; BNE done(其他表bank)
    code += bytes([0xA5, 0x88, 0xC9, 0xBD]); _b(0xB0)   # LDA $88; CMP #$BD; BCS done(文本表$BD4C+)
    code += bytes([0xAD, 0x50, 0x04, 0x09, 0xC0, 0x8D, 0xFF, 0x5F])  # 深bank: $0450|$C0 → shadow
    _b(0xD0)                                        # BNE done(值≥$C0 恒真)
    code[_main] = len(code) - (_main + 1)           # main:
    code += bytes([0xA5, 0x88, 0xC9, 0xBC]); _b(0x90)   # LDA $88; CMP #$BC; BCC done(非句表读)
    code += bytes([0xAD, 0x50, 0x04, 0x09, 0x80, 0x8D, 0xFF, 0x5F])  # 默认 A bank
    for _i, (hi, lo, span, bk) in enumerate(runs):
        code += bytes([0xA5, 0x88, 0xC9, hi, 0xD0, 0x00]); _n1 = len(code) - 1   # ≠hi → next
        code += bytes([0xA5, 0x87, 0x38, 0xE9, lo, 0xC9, span, 0xB0, 0x00]); _n2 = len(code) - 1  # lo距≥span → next
        code += bytes([0xA9, bk, 0x8D, 0xFF, 0x5F])                                # 命中 → B bank
        if _i + 1 < len(runs): _b(0xD0)             # BNE done(bk≠0 恒真;末块直接落 done)
        code[_n1] = len(code) - (_n1 + 1); code[_n2] = len(code) - (_n2 + 1)       # next:
    for p in fix: code[p] = len(code) - (p + 1)     # done:
    code += bytes([0xA5, 0x7E, 0x8D, 0x15, 0x51, 0x60])   # LDA $7E; STA $5115; RTS
    assert len(code) <= 0x5A, f"hook v2 超长 {len(code)}B>90(B块过多,减 B_SENTS 连续段数)"
    return bytes(code)
_hook = _asm_hook_v2()
_payload = _hook + bytes(0x5A - len(_hook)) + bytes([0x80])
assert len(_payload) == 0x5B
# ④ bank127 开机 shim:上电 $5117=$FF→$E000=bank127(我们的副本)。把副本里 $E9B1 的
#   `LDA #$BE; STA $5114`(5B) 改 `JMP $E800`;$E800 blob 把 payload($E820)拷入 ExRAM $5FA5
#   (此刻 $5104=2 已设,NMI/IRQ 未开),补执行被顶掉的指令,再 `JMP $E9B6` 跳回原封不动的
#   `LDA #$BF; STA $5117`——★切换必须发生在原位置:STA $5117 一执行 $E000 即切到 bank63,
#   下一条指令从 bank63 同地址取;仅当切换点后内容两 bank 一致(副本未改处)才能无缝交接。
#   (教训:曾把切换搬进 shim 尾部→切换后从 bank63 $E812 取指=无关代码→上电即崩。)
#   bank127 除启动路径外永不执行→blob/payload 随便放;bank63 本尊保持原样。
assert rom[BANK127 + 0x9B1:BANK127 + 0x9B6] == bytes([0xA9, 0xBE, 0x8D, 0x14, 0x51]), "bank127 reset 副本异常"
rom[BANK127 + 0x9B1:BANK127 + 0x9B6] = bytes([0x4C, 0x00, 0xE8, 0xEA, 0xEA])   # JMP $E800
_shim = bytes([
    0xA2, 0x00,        # LDX #$00
    0xBD, 0x20, 0xE8,  # l: LDA $E820,X
    0x9D, 0xA5, 0x5F,  # STA $5FA5,X
    0xE8,              # INX
    0xE0, 0x5B,        # CPX #$5B
    0xD0, 0xF5,        # BNE l
    0xA9, 0xBE,        # LDA #$BE
    0x8D, 0x14, 0x51,  # STA $5114      被顶掉的原指令($5114=PRG0 bank)
    0x4C, 0xB6, 0xE9,  # JMP $E9B6      回原切换指令(bank127/63 同内容→无缝)
])
rom[BANK127 + 0x800:BANK127 + 0x800 + len(_shim)] = _shim
rom[BANK127 + 0x820:BANK127 + 0x820 + 0x5B] = _payload

for n in include + sorted(b_c2c):
    text = tr[n]; c2c = b_c2c.get(n) or scene_c2c[gui_scene[n]]; bs = bytearray(); i = 0
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
