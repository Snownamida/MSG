#!/usr/bin/env python3
"""第一章「完美」判据审计器。

汇总所有遍历数据(seqrun 场景映射 + digger 穷尽 + crawl 状态图),得狭义第一章可达句全集,
减去 build 已中文的(include)+ 密语系统句,列出漏网(可达但未翻的句)。漏网为空 = 遍历所及全中文。

「完美」= 狭义第一章(NEW GAME→场景14 选休息 为止)可达对话全中文。边界见 docs/LOCALIZATION.md。
判据与 build_ch1_mb.py 的 include 逻辑保持一致(改判据须两处同步)。

用法: audit.py            (只用项目 reversing/data/ 数据)
      audit.py <extra_dir> (额外并入某目录下的 map_*.json / dig_*.tsv / scene_map.tsv,如深爬输出)
"""
import json, glob, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "reversing", "data")
LUA_OFF = 1                                   # Lua trace N = msgtool 句号 − 1
B_SENTS = {187, 204, 205, 206, 207}
STAGE2_FROM = 158                             # 158+ = 升空/空间站/STAFF/第二章
DENY_SCENE = {0x00, 0x16}                     # 密语屏(不译) / 升空(第二章)

reach = set()
def add(n):
    if isinstance(n, int): reach.add(n + LUA_OFF)

# seqrun 场景映射(N/SEQ 行) + 可选额外目录
srcs = [os.path.join(DATA, "ch1_scene_map.tsv")]
extra = sys.argv[1] if len(sys.argv) > 1 else None
if extra:
    srcs += glob.glob(os.path.join(extra, "scene_map.tsv"))
for f in srcs:
    if not os.path.exists(f): continue
    for l in open(f):
        p = l.split()
        if len(p) >= 2 and p[0] in ("N", "SEQ") and p[1].isdigit(): add(int(p[1]))

# digger 穷尽话题
dig_dirs = [DATA] + ([extra] if extra else [])
for d in dig_dirs:
    for f in glob.glob(os.path.join(d, "dig_*.tsv")):
        for l in open(f):
            p = l.split()
            if len(p) >= 3 and p[0] == "N": add(int(p[1]))
    # digger 汇总的场景归属文件
    f = os.path.join(d, "ch1_dig_scene.tsv")
    if os.path.exists(f):
        for l in open(f):
            p = l.split()
            if len(p) >= 2 and p[0].isdigit(): add(int(p[0]))

# crawl 状态图(项目 + 额外目录的 map_*.json / deep_*.json)
maps = [os.path.join(DATA, "chapter_map.json")]
if extra: maps += glob.glob(os.path.join(extra, "*.json"))
for mf in maps:
    if not os.path.exists(mf): continue
    try:
        cm = json.load(open(mf))
        scenes = cm.get("scenes", {"_": cm.get("nodes", [])})
        for nodes in scenes.values():
            for nd in nodes:
                for e in nd.get("options", []):
                    for s in e.get("sentences", []): add(s)
    except Exception:
        pass

# 场景归属(判密语/升空)
gui = {}
for l in open(os.path.join(DATA, "ch1_scene_map.tsv")):
    if l.startswith("SEQ"):
        _, n, b = l.split(); gui.setdefault(int(n) + LUA_OFF, int(b, 16))
fdig = os.path.join(DATA, "ch1_dig_scene.tsv")
if os.path.exists(fdig):
    for l in open(fdig):
        p = l.split()
        if len(p) >= 2 and p[0].isdigit(): gui.setdefault(int(p[0]) + LUA_OFF, int(p[1], 16))

DIG_EXTRA = {n for n in gui if 217 < n <= 281}
def translated(n):
    if n in B_SENTS: return True
    if gui.get(n) == 0x00: return False       # 密语屏保原版日文
    return (n <= 157 or 174 <= n <= 217 or n in DIG_EXTRA)

narrow = [n for n in sorted(reach) if n < STAGE2_FROM and gui.get(n) not in DENY_SCENE]
untrans = [n for n in narrow if not translated(n)]

print(f"汇总可达句(全): {len(reach)}" + (f"  范围 {min(reach)}-{max(reach)}" if reach else ""))
print(f"狭义第一章(<{STAGE2_FROM},非密语/升空)可达: {len(narrow)}  已中文: {sum(1 for n in narrow if translated(n))}")
print(f"★漏网(可达但未翻): {untrans}")
print("完美判据:" + ("✓ PASS(遍历所及全中文)" if not untrans else "✗ FAIL(需装箱上述句)"))
