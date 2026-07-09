#!/usr/bin/env python3
"""演出数据区扫描器 —— 扫一段演出区,自动分剧情段,输出目录(全章静态转储基础)。

演出区是"剧情句子按号线性存储"的数据(每条 `40 00·4E<句>·41`),段内句号连续、段间大跳。
本工具从给定 (bank,addr) 线性扫描,按 max_gap 自动切剧情段,输出每段的句号范围+首句译文。
配合 autoscript(单段完整提取)与库0入口枚举,可把第一章演出对话静态转储成目录。

用法: scandump.py <bank_hex> <addr_hex> [count] [max_gap]
"""
import sys, os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "reversing", "senmap"))
from scriptdis import disasm_script, sent


def segments(bank, addr, count=400, max_gap=50):
    """扫描 → [(首句号, 末句号, [句号...]) ...] 按连续性分段。"""
    ins = disasm_script(bank, addr, count)
    sents = [sn for a, c, raw, sn in ins if sn is not None]
    if not sents:
        return []
    segs, cur = [], [sents[0]]
    for s in sents[1:]:
        if abs(s - cur[-1]) <= max_gap:
            cur.append(s)
        else:
            segs.append(cur); cur = [s]
    segs.append(cur)
    return [(g[0], g[-1], g) for g in segs]


if __name__ == "__main__":
    bank = int(sys.argv[1], 16); addr = int(sys.argv[2], 16)
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 400
    max_gap = int(sys.argv[4]) if len(sys.argv) > 4 else 50
    segs = segments(bank, addr, count, max_gap)
    print(f"=== 演出区 bank{bank:02X}:${addr:04X} 扫描 → {len(segs)} 个剧情段 ===")
    for s, e, g in segs:
        print(f"  段 句{s}-{e} ({len(g)}句): {sent(s)[:30]}")
