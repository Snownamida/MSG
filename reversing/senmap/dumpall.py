#!/usr/bin/env python3
"""全游戏演出对话系统提取器(双轨的白盒轨·批量版)。

库0 是"演出脚本入口表"(见 SCRIPT_ENGINE.md):库0句号 --$F01D--> 句子指针 --读3字节--> 演出脚本地址。
遍历库0所有句号,对每个算出演出地址、scandump 提剧情段,汇总所有段 → 全游戏演出对话覆盖。
不依赖动态遍历(绕开特殊交互场景卡点),给出"可达对话全集"。按句号范围可切各章。

用法: dumpall.py [max_libidx]   默认扫库0句号 1..1500
"""
import sys, os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "reversing", "senmap"))
from autoscript import script_entry, BASE_BEACH
from scandump import segments
from scriptdis import sent

MAXIDX = int(sys.argv[1]) if len(sys.argv) > 1 else 1500

segs = {}          # 演出地址 (bank,addr) → (首句, 末句, 句数, 库0入口)
for n in range(1, MAXIDX):
    try:
        sb, sa = script_entry(n, BASE_BEACH)
    except Exception:
        continue
    if not (0x80 <= sb <= 0xFF and 0xA000 <= sa <= 0xBFFF):
        continue
    ss = segments(sb, sa, 80)
    if not ss:
        continue
    s, e, g = ss[0]
    # 有效演出段:句号在剧本范围、段不过长、至少2句连续
    if 1 <= s <= 2781 and 0 <= e - s < 200 and len(g) >= 2:
        key = (sb, sa)
        if key not in segs:
            segs[key] = (s, e, len(g), n)

# 汇总覆盖的句号
covered = set()
for (sb, sa), (s, e, g, n) in segs.items():
    covered.update(range(s, e + 1))

print(f"库0扫 1..{MAXIDX}:命中 {len(segs)} 个演出段,覆盖 {len(covered)} 个句号")
# 覆盖句号按连续段汇总
cs = sorted(covered)
ranges = []
if cs:
    a = b = cs[0]
    for x in cs[1:]:
        if x == b + 1:
            b = x
        else:
            ranges.append((a, b)); a = b = x
    ranges.append((a, b))
print("覆盖句号连续区间:")
for a, b in ranges:
    print(f"  {a}-{b} ({b - a + 1}句)  首句: {sent(a)[:26]}")
