#!/usr/bin/env python3
"""合并 14 批译文 → 完整译文表，做术语归一 + 全量校验。

- 覆盖：1..2781 全在、无重复。
- 控制码保真：每句 `~XXXX~` 多重集与原文一致（空源句允许空译）。
- 术语归一：并行翻译产生的表外专名分歧，统一到主流/合理译法（保留剧情双关 维维斯≠维瓦切）。
- 输出 `translation/script_zh.tsv`（`句号<TAB>中文`，版权 gitignore），供 reinsert_full.py 回写。
"""
import re, json, os, sys

OUT_DIR = os.path.join(os.path.dirname(__file__), "out")
SCRIPT_JA = os.path.join(os.path.dirname(__file__), "..", "scratch_script.json")
DST = os.path.join(os.path.dirname(__file__), "script_zh.tsv")
CTRL = re.compile(r"~[0-9A-Fa-f]+~")

# 术语归一（默认取主流；维维斯=ヴィヴェイス 的英式误读双关，勿并入 维瓦切=ヴィヴァーチェ）
NORMALIZE = [
    ("阿梓", "梓"),
    ("昌太", "正忠"),
    ("薇薇雅切", "维瓦切"), ("薇瓦切", "维瓦切"),
    ("薇薇艾斯", "维维斯"),
    ("月颜号", "月面号"), ("月之脸", "月面号"), ("月脸号", "月面号"),
    ("麦克莓", "麦克贝瑞斯"),
    (re.compile(r"麦克贝瑞(?!斯)"), "麦克贝瑞斯"),
    ("史托克", "斯托克"),
]


def normalize(s):
    for pat, rep in NORMALIZE:
        s = pat.sub(rep, s) if hasattr(pat, "sub") else s.replace(pat, rep)
    return s


def main():
    ja = {d["n"]: d["ja"] for d in json.load(open(SCRIPT_JA, encoding="utf-8"))}
    tr = {}
    for f in sorted(os.listdir(OUT_DIR)):
        if not f.endswith(".tsv") or ".bad" in f:
            continue
        for line in open(os.path.join(OUT_DIR, f), encoding="utf-8"):
            line = line.rstrip("\n")
            if "\t" in line:
                ns, zh = line.split("\t", 1)
                tr[int(ns)] = zh
            elif line.strip().isdigit():
                tr.setdefault(int(line.strip()), "")

    # 空源/空格占位句：译文缺失时回落到原文（保持空白排版）
    for n in range(1, 2782):
        if ja[n] != "" and tr.get(n, "").strip() == "":
            tr[n] = ja[n]

    # 归一
    hits = 0
    for n in tr:
        z = normalize(tr[n])
        if z != tr[n]: hits += 1
        tr[n] = z

    # 校验
    missing = [n for n in range(1, 2782) if n not in tr]
    badctrl = [n for n in range(1, 2782) if n in tr and
               sorted(x.upper() for x in CTRL.findall(ja[n])) !=
               sorted(x.upper() for x in CTRL.findall(tr[n]))]
    print(f"覆盖 {len(tr)}/2781，缺失 {len(missing)} {missing[:10]}")
    print(f"归一命中 {hits} 句；控制码不符 {len(badctrl)} {badctrl[:20]}")
    if missing or badctrl:
        print("⚠ 仍有问题，未写出。", file=sys.stderr)
        return
    with open(DST, "w", encoding="utf-8") as f:
        for n in range(1, 2782):
            f.write(f"{n}\t{tr[n]}\n")
    uniq = set(c for n in tr for c in re.sub(CTRL, "", tr[n]))
    print(f"✓ 写出 {DST}；唯一字符（含标点，去控制码）约 {len(uniq)}")


if __name__ == "__main__":
    main()
